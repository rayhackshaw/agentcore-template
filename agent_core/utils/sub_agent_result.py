"""
SubAgentResult utility for streaming sub-agent events.

Wraps events from sub-agents that are invoked as tools, so their streaming
events (thinking, reasoning, tool usage) can ride through the orchestrator
agent's own stream inside a `tool_stream_event`.
"""
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class SubAgentResult:
    """
    Attributes:
        agent: The Agent instance (or a plain label string) that produced this event
        event: The raw event dict from the agent's stream
    """
    agent: Any
    event: Dict[str, Any]


def filter_event_metadata(event: dict) -> dict:
    """Strip Strands/Bedrock internal framework fields before an event leaves this service."""
    if not isinstance(event, dict):
        return event

    return {
        k: v for k, v in event.items()
        if k not in (
            "agent",
            "model",
            "system_prompt",
            "tool_config",
            "messages",
            "event_loop_cycle_id",
            "event_loop_parent_cycle_id",
            "request_state",
            "event_loop_cycle_trace",
            "event_loop_cycle_span",
        )
    }
