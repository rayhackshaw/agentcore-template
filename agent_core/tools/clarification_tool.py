"""
Clarification tool for presenting interactive options to the user.

Two uses:
1. Ask a clarifying question when the request is ambiguous.
2. Present a plan for Yes/No/Custom approval.

For plan approval, the tool mints a `planId` and stashes the plan text in a
bounded LRU. The caller's Yes/No buttons then send a lightweight
`plan_response` frame carrying that id — see orchestrator.py's
__PLAN_APPROVED__/__PLAN_REJECTED__ handling — instead of a fake "Yes,
proceed" user message.
"""

from collections import OrderedDict
from typing import AsyncIterator
from uuid import uuid4

from strands import tool

from agent_core.utils import SubAgentResult, get_agent_logger

logger = get_agent_logger("clarification_tool")

_PENDING_PLANS: "OrderedDict[str, dict]" = OrderedDict()
_PENDING_PLANS_MAX = 64


def store_pending_plan(plan_text: str) -> str:
    plan_id = f"plan-{uuid4().hex[:8]}"
    _PENDING_PLANS[plan_id] = {"text": plan_text}
    while len(_PENDING_PLANS) > _PENDING_PLANS_MAX:
        _PENDING_PLANS.popitem(last=False)
    return plan_id


def pop_pending_plan(plan_id: str) -> dict | None:
    return _PENDING_PLANS.pop(plan_id, None)


def peek_pending_plan(plan_id: str) -> dict | None:
    return _PENDING_PLANS.get(plan_id)


@tool
async def ask_clarification(question: str, options: list, allow_custom: bool = True, plan: str = "") -> AsyncIterator:
    """
    Present clickable clarification options to the user.

    1. **Clarification** (missing scope/context): set `question`, leave `plan` empty.
    2. **Plan approval**: set `plan` to your full plan text, leave `question` empty.
       The plan is displayed to the user above Yes/No/Custom buttons.

    Args:
        question: Clarification question shown above the options. Empty string for plan approval.
        options: List of {"label": short button text, "value": full message sent when clicked}.
        allow_custom: Whether to show a free-text input alongside the options.
        plan: Required for plan approval — your full plan text for the user to review.
    """
    logger.info(f"[CLARIFICATION] question={question!r} options={[o.get('label') for o in options]}")

    plan_id: str | None = None
    if plan:
        plan_id = store_pending_plan(plan)
        logger.info(f"[CLARIFICATION] Plan stored planId={plan_id} chars={len(plan)}")

        yield SubAgentResult(
            agent="clarification",
            event={"type": "plan", "content": plan, "planId": plan_id},
        )

    data: dict = {"question": question, "options": options, "allowCustom": allow_custom}
    if plan_id:
        data["planId"] = plan_id

    yield SubAgentResult(
        agent="clarification",
        event={"type": "clarification_options", "data": data},
    )

    option_labels = ", ".join(opt.get("label", "") for opt in options)
    yield f"I've presented the user with options: {option_labels}. Waiting for their selection."
