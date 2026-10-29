"""
CLI runner for local agent invocation. Calls main_invoke() directly in-process
— no HTTP server, no frontend. Streams and pretty-prints all agent events.

Usage:
    cd agentcore
    uv run agentcore-invoke "what can you do?"
    uv run agentcore-invoke "do something that needs a tool" --mode standard
    uv run agentcore-invoke "handle this with attached context" --mode contextual
"""

import argparse
import asyncio
import json
import logging
import sys
import textwrap
import time
import uuid
from dataclasses import is_dataclass

logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("agent_core.interrupt_hook").setLevel(logging.WARNING)


def _colour(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def _print_event(event: dict):
    t = event.get("type", "unknown")

    if t == "thinking":
        content = event.get("content", "")
        print(_colour("36", "[thinking] ") + textwrap.shorten(content, width=120, placeholder="…"))

    elif t == "status":
        print(_colour("33", "[status]   ") + event.get("status", ""))

    elif t == "tool_query":
        print(_colour("35", "[query]    ") + textwrap.shorten(str(event.get("query", "")), width=120, placeholder="…"))

    elif t == "tool_result":
        rows = event.get("total_rows", 0)
        cols = ", ".join(event.get("columns", []))
        print(_colour("35", "[result]   ") + f"{rows} rows — {cols}")

    elif t == "content_delta":
        print(event.get("delta", ""), end="", flush=True)

    elif t == "clarification_options":
        print(_colour("33", "[clarify]  ") + json.dumps(event.get("data", {}), ensure_ascii=False))

    elif t == "plan":
        print(_colour("33", "[plan]     ") + textwrap.shorten(event.get("content", ""), width=200, placeholder="…"))

    elif t in ("agent_complete", "done"):
        print()
        print(_colour("32", "[done]"))

    elif t == "error":
        print(_colour("31", "[error]    ") + event.get("error", ""))

    # silently skip internal/metadata events


async def run(prompt: str, mode: str):
    from agent_core.chat.orchestrator import main_invoke

    conversation_id = str(uuid.uuid4())
    payload = {
        "prompt": prompt,
        "mode": mode,
        "conversationId": conversation_id,
        "sessionInstanceId": f"{mode}-local-{conversation_id}",
    }

    print(_colour("90", f"mode={mode}  conversation={conversation_id}"))
    print(_colour("90", "─" * 60))

    total_input = 0
    total_output = 0
    start = time.monotonic()

    async for event in main_invoke(payload):
        if not isinstance(event, dict):
            if is_dataclass(event) and not isinstance(event, type):
                inner = getattr(event, "event", None)
                if isinstance(inner, dict):
                    _print_event(inner)
            continue

        usage = event.get("event", {}).get("metadata", {}).get("usage", {})
        if usage:
            total_input += usage.get("inputTokens", 0)
            total_output += usage.get("outputTokens", 0)

        _print_event(event)

    elapsed = time.monotonic() - start
    mins, secs = divmod(int(elapsed), 60)
    elapsed_str = f"{mins}m{secs:02d}s" if mins else f"{secs}s"

    print()
    print(_colour("90", "─" * 60))
    if total_input or total_output:
        print(_colour("90", f"tokens  in={total_input:,}  out={total_output:,}  total={total_input + total_output:,}  time={elapsed_str}"))


def main():
    parser = argparse.ArgumentParser(description="Invoke the agentcore orchestrator locally")
    parser.add_argument("prompt", help="The message to send")
    parser.add_argument(
        "--mode",
        choices=["quick", "standard", "contextual"],
        default="standard",
        help="Chat mode (default: standard)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run(args.prompt, args.mode))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
