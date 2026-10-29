"""
Generic "agent as tool" sub-agent. Mirrors the shape every sub-agent in this
pattern follows: a module-level BedrockModel + cached Agent instances, an
@tool async-generator wrapper that streams SubAgentResult events back to the
orchestrator, and an InterruptHook so a mid-turn cancellation reaches it.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from strands import Agent, tool
from strands.models import BedrockModel, CacheConfig

from agent_core.tools.example_tool import example_data_lookup
from agent_core.utils import (
    SubAgentResult,
    get_agent_logger,
    load_prompt,
    log_agent_message,
    log_function_call,
)
from agent_core.utils.interrupt_hook import InterruptHook

logger = get_agent_logger("worker_agent")

WORKER_MODEL_ID = os.getenv("WORKER_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")


@tool
async def emit_thinking_step(message: str) -> AsyncIterator:
    """
    Emit a brief user-facing narration of what this worker is doing or found.
    This is for the USER, not a reasoning scratchpad — announce outcomes,
    don't narrate the decision process.

    Args:
        message: Brief plain-language narration.
    """
    try:
        yield SubAgentResult(agent="worker_agent", event={"type": "thinking", "content": message})
        yield "Thinking step emitted successfully"
    except Exception as e:
        logger.error(f"[WORKER] Failed to yield thinking step: {e}")
        yield "Thinking step emission failed (non-critical)"


@tool
async def worker_invoke(user_message: str, context_key: str | None = None) -> AsyncIterator:
    """
    Run a sub-agent that can call external tools and return a synthesised answer.

    Args:
        user_message: The task to hand to the worker.
        context_key: Optional cache key (e.g. a dataset or tenant id). Sequential
            calls with the same key reuse one Agent so conversation history
            carries across; a concurrent call on a busy key gets a throwaway
            agent instead of hitting Strands' single-stream concurrency limit.
    """
    log_function_call(logger, "worker_agent", "worker_invoke", {"user_message": user_message, "context_key": context_key})
    log_agent_message(logger, "worker_agent", "RECEIVED", user_message)

    async with _acquire_worker_agent(context_key) as agent:
        result = None
        async for event in agent.stream_async(user_message):
            yield SubAgentResult(agent=agent, event=event)
            if "result" in event:
                result = event["result"]

        if result and hasattr(result, "message") and isinstance(result.message, dict):
            content = result.message.get("content", [])
            if isinstance(content, list):
                text_parts = [item["text"] for item in content if isinstance(item, dict) and "text" in item]
                if text_parts:
                    yield "".join(text_parts)
                    return

        if result:
            yield str(result.message if hasattr(result, "message") else result)
        else:
            logger.warning("[WORKER] No result received from worker_agent stream")
            yield "No result received from worker agent"


bedrock_model = BedrockModel(
    model_id=WORKER_MODEL_ID,
    region_name=BEDROCK_REGION,
    streaming=True,
    cache_config=CacheConfig(tools_ttl=True),
)

_base_system_prompt = load_prompt("worker_agent_prompt.txt")

_agent_cache: dict[str, Agent] = {}
_agents_in_use: set[str] = set()
_AGENT_CACHE_MAX = 32


def _make_worker_agent(system_prompt: list[dict]) -> Agent:
    agent = Agent(
        model=bedrock_model,
        system_prompt=system_prompt,
        tools=[example_data_lookup, emit_thinking_step],
    )
    agent.hooks.add_hook(InterruptHook(agent))
    return agent


@asynccontextmanager
async def _acquire_worker_agent(context_key: str | None):
    """Cache one Agent per context_key so sequential calls keep history.
    A busy key under concurrent tool calls gets a throwaway agent instead of
    Strands raising ConcurrencyException on a second stream_async."""
    cache_key = context_key or "__default__"
    cached = _agent_cache.get(cache_key)
    held_key: str | None = None

    if cached is not None and cache_key not in _agents_in_use:
        _agents_in_use.add(cache_key)
        held_key = cache_key
        agent = cached
    else:
        system_prompt: list[dict] = [
            {"text": _base_system_prompt},
            {"cachePoint": {"type": "default"}},
        ]
        agent = _make_worker_agent(system_prompt)

        if cached is None:
            if len(_agent_cache) >= _AGENT_CACHE_MAX:
                _agent_cache.pop(next(iter(_agent_cache)))
            _agent_cache[cache_key] = agent
            _agents_in_use.add(cache_key)
            held_key = cache_key

    try:
        yield agent
    finally:
        if held_key is not None:
            _agents_in_use.discard(held_key)
