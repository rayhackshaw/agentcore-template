"""
Interrupt checker tool — lets a sub-agent check mid-task whether the user
has requested cancellation, rather than waiting for the next tool boundary
where InterruptHook would catch it.
"""

from strands import tool, ToolContext

from agent_core.utils import get_agent_logger
from agent_core.utils.interrupt_manager import is_interrupted

logger = get_agent_logger("interrupt_checker")


@tool(context=True)
def check_user_interrupt(tool_context: ToolContext) -> str:
    """
    Check if the user has requested to cancel this conversation. Call this
    periodically during long-running operations.
    """
    conversation_id = tool_context.agent.state.get("conversation_id")

    if not conversation_id:
        return "No conversation ID found in state, continuing execution"

    if is_interrupted(conversation_id):
        logger.info(f"[INTERRUPT_CHECKER] User interrupt detected for conversation {conversation_id}")
        tool_context.interrupt(
            "user-cancellation",
            reason={"message": "User cancelled execution", "conversation_id": conversation_id},
        )
        return "User has cancelled execution"

    return "Execution continuing normally"
