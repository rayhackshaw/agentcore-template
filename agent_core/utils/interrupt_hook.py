"""
Hook that checks for user-initiated interrupts before tool execution.
Integrates with Strands Agent BeforeToolCallEvent.
"""

from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent

from .logging import get_agent_logger

logger = get_agent_logger("interrupt_hook")

_user_interrupt: bool = False


def set_user_interrupt(value: bool) -> None:
    """Process-level flag. The __INTERRUPT_REQUEST__ sentinel arrives as a
    separate invocation from the one being interrupted, so this has to live
    outside any single Agent instance's state."""
    global _user_interrupt
    _user_interrupt = value


def get_user_interrupt() -> bool:
    return _user_interrupt


class InterruptHook(HookProvider):
    """Checks for interrupt signals before every tool call on the agent it's attached to."""

    def __init__(self, agent):
        self.agent = agent

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.check_interrupt)

    def check_interrupt(self, event: BeforeToolCallEvent) -> None:
        conversation_id = self.agent.state.get("conversation_id") or "unknown"

        if _user_interrupt is True:
            logger.info(
                f"[INTERRUPT_HOOK] User interrupt detected for conversation {conversation_id}, "
                f"cancelling tool: {event.tool_use.get('name')}"
            )
            event.cancel_tool = "Execution cancelled by user"
