"""
Orchestrator entrypoint. Mirrors unified_chat_agent.py: one Agent whose tools
are themselves sub-agents, streamed through a single AgentCore entrypoint.
"""

import os
from dataclasses import is_dataclass

from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel, CacheConfig

from agent_core.utils import get_agent_logger, filter_event_metadata
from agent_core.utils.interrupt_manager import register_conversation, cleanup_conversation

from .modes import get_system_prompt_for_mode
from .tools import get_tools_for_mode, set_interrupt_flags

logger = get_agent_logger("orchestrator")

main_app = BedrockAgentCoreApp()

ORCHESTRATOR_MODEL_ID = os.getenv("ORCHESTRATOR_MODEL_ID", "us.anthropic.claude-opus-4-6")
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")

bedrock_model = BedrockModel(
    model_id=ORCHESTRATOR_MODEL_ID,
    region_name=BEDROCK_REGION,
    streaming=True,
    cache_config=CacheConfig(tools_ttl=True),
)


def _is_raw_bedrock_frame(sub_event) -> bool:
    """A raw Strands/Bedrock frame from a sub-agent's own LLM stream
    (contentBlockDelta, messageStop, etc). Forwarding these would make
    whatever consumes this stream treat sub-agent text as the orchestrator's
    own output — duplicating deltas and flushing buffers prematurely."""
    return isinstance(sub_event, dict) and "event" in sub_event


def _wrap_with_context(user_message: str, context: dict | None) -> str:
    """Prepend arbitrary pinned context as an XML block. Each entry may carry
    an id (or ids) alongside its display label — agents should filter on the
    id, not the label, so behaviour stays deterministic if labels drift."""
    if not context or not isinstance(context, dict):
        return user_message

    lines: list[str] = []
    for key, value in context.items():
        if value is None or value == "":
            continue
        if isinstance(value, dict):
            label = value.get("label")
            ids = value.get("ids") or ([value["id"]] if value.get("id") is not None else [])
            if not label:
                continue
            if len(ids) == 1:
                lines.append(f'  <{key} id="{ids[0]}">{label}</{key}>')
            elif len(ids) > 1:
                joined = ",".join(str(i) for i in ids)
                lines.append(f'  <{key} ids="{joined}">{label}</{key}>')
            else:
                lines.append(f"  <{key}>{label}</{key}>")
        else:
            lines.append(f"  <{key}>{value}</{key}>")

    if not lines:
        return user_message
    block = "<context>\n" + "\n".join(lines) + "\n</context>"
    return f"{block}\n\n{user_message}"


@main_app.entrypoint
async def main_invoke(payload):
    """
    Payload shape:
        prompt, conversationId, sessionInstanceId, mode,
        contextPayload, corrections, userContext
    """
    user_message = payload.get("prompt")
    conversation_id = payload.get("conversationId")
    session_instance_id = payload.get("sessionInstanceId")
    mode = payload.get("mode", "standard")
    context_payload = payload.get("contextPayload")
    corrections = payload.get("corrections", [])
    user_context = payload.get("userContext") or None

    if user_message == "__WARMUP__":
        yield {"type": "status", "status": "warmup_ack"}
        return

    if user_message == "__INTERRUPT_REQUEST__":
        logger.info(f"[ORCHESTRATOR] Interrupt request for conversation {conversation_id}")
        set_interrupt_flags(True)
        yield {"type": "status", "status": "interrupt_acknowledged"}
        return

    set_interrupt_flags(False)

    # Plan approve/reject sentinel. The caller rewrites a plan_response frame
    # into __PLAN_APPROVED__:<planId> / __PLAN_REJECTED__:<planId> so the
    # orchestrator can resume without fabricating a fake user turn.
    if isinstance(user_message, str) and (
        user_message.startswith("__PLAN_APPROVED__:") or user_message.startswith("__PLAN_REJECTED__:")
    ):
        from agent_core.tools.clarification_tool import pop_pending_plan

        is_approve = user_message.startswith("__PLAN_APPROVED__:")
        plan_id = user_message.split(":", 1)[1].strip()
        pending = pop_pending_plan(plan_id) if plan_id else None
        plan_text = (pending or {}).get("text", "") if pending else ""

        if is_approve:
            user_message = (
                "The user approved the plan below. Execute it now — do NOT ask for "
                "confirmation again, do NOT re-plan.\n\n"
                f"<approved_plan>\n{plan_text}\n</approved_plan>"
                if plan_text
                else "The user approved the plan you just proposed. Execute it now — do NOT ask for confirmation again."
            )
        else:
            user_message = (
                "The user rejected the plan below. Ask a brief follow-up to understand "
                "what to change, then propose a revised plan.\n\n"
                f"<rejected_plan>\n{plan_text}\n</rejected_plan>"
                if plan_text
                else "The user rejected the plan you just proposed. Ask a brief follow-up to understand what to change."
            )
        logger.info(
            f"[ORCHESTRATOR] Resolved plan sentinel planId={plan_id} decision="
            f"{'approved' if is_approve else 'rejected'} plan_text_len={len(plan_text)}"
        )

    if conversation_id:
        register_conversation(conversation_id)

    system_prompt = get_system_prompt_for_mode(mode, context_payload, corrections=corrections)
    tools = get_tools_for_mode(mode, has_context_payload=bool(context_payload))

    agent = Agent(
        model=bedrock_model,
        system_prompt=[
            {"text": system_prompt},
            {"cachePoint": {"type": "default"}},
        ],
        tools=tools,
    )

    if conversation_id:
        agent.state.set("conversation_id", conversation_id)
    if session_instance_id:
        agent.state.set("session_instance_id", session_instance_id)
    if context_payload:
        agent.state.set("context_payload", context_payload)

    stream = agent.stream_async(_wrap_with_context(user_message, user_context))

    try:
        async for event in stream:
            if isinstance(event, dict):
                tool_stream = event.get("tool_stream_event", {}).get("data")

                if tool_stream:
                    if is_dataclass(tool_stream) and not isinstance(tool_stream, type):
                        sub_event = tool_stream.event
                        if _is_raw_bedrock_frame(sub_event):
                            continue
                        filtered = _filter_user_hallucinations(filter_event_metadata(sub_event))
                        if filtered is not None:
                            yield filtered
                        continue

                    if isinstance(tool_stream, dict) and "event" in tool_stream:
                        sub_event = tool_stream.get("event", {})
                        if _is_raw_bedrock_frame(sub_event):
                            continue
                        filtered = _filter_user_hallucinations(filter_event_metadata(sub_event))
                        if filtered is not None:
                            yield filtered
                        continue

            if isinstance(event, dict):
                filtered = _filter_user_hallucinations(filter_event_metadata(event))
                if filtered is not None:
                    yield filtered
            else:
                yield event

    finally:
        if conversation_id:
            cleanup_conversation(conversation_id)


def _filter_user_hallucinations(event: dict) -> dict | None:
    """Cut off any assistant content that hallucinates a fake user turn.
    If every content item gets filtered, drop the event entirely."""
    if not isinstance(event, dict):
        return event

    if "message" in event and isinstance(event["message"], dict):
        content = event["message"].get("content", [])
        if isinstance(content, list):
            filtered_content = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    text = item["text"]
                    if "User:" in text:
                        logger.warning("[ORCHESTRATOR] Filtering hallucinated user turn from assistant content")
                        text = text.split("User:")[0]
                        if not text.strip():
                            continue
                        item = {**item, "text": text}
                    filtered_content.append(item)
                else:
                    filtered_content.append(item)

            if not filtered_content and content:
                return None

            event = {**event, "message": {**event["message"], "content": filtered_content}}

    return event


if __name__ == "__main__":
    main_app.run()
