"""
Mode -> tool list mapping. Mirrors chat_tools.py: each mode gets a different
tool surface so the model can't reach for operations that don't make sense
in that context.
"""


def get_tools_for_mode(mode: str, has_context_payload: bool = False) -> list:
    if mode == "quick":
        return get_quick_tools()

    if mode == "contextual" or has_context_payload:
        return get_standard_tools() + get_contextual_tools()

    return get_standard_tools()


def get_quick_tools() -> list:
    from agent_core.sub_agents.worker_agent import worker_invoke

    return [worker_invoke]


def get_standard_tools() -> list:
    from agent_core.sub_agents.worker_agent import worker_invoke
    from agent_core.tools.clarification_tool import ask_clarification
    from agent_core.tools.interrupt_checker import check_user_interrupt

    return [ask_clarification, worker_invoke, check_user_interrupt]


def get_contextual_tools() -> list:
    """Extension point: tools that only make sense when an external context
    payload is attached (e.g. "update the attached record")."""
    return []


def set_interrupt_flags(value: bool):
    from agent_core.utils.interrupt_hook import set_user_interrupt

    set_user_interrupt(value)
