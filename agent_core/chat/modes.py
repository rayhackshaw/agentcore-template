"""
Mode -> system prompt mapping. Mirrors modes.py: three modes trading off
speed vs. capability vs. context-awareness.
"""

import json

from agent_core.utils import load_prompt


def get_system_prompt_for_mode(mode: str, context_payload: dict = None, corrections: list = None) -> str:
    if mode == "quick":
        return _build_corrections_block(corrections) + load_prompt("quick_agent_prompt.txt")

    if mode == "contextual" or context_payload:
        return get_contextual_mode_prompt(context_payload, corrections)

    return _build_corrections_block(corrections) + load_prompt("standard_agent_prompt.txt")


def _build_corrections_block(corrections: list | None) -> str:
    """XML block of known-good guidance to prepend to any system prompt."""
    if not corrections:
        return ""
    lines = ["<corrections>", "Apply this known-good guidance when answering:\n"]
    for i, c in enumerate(corrections, 1):
        lines.append(f"## Correction {i}: {c['title']}")
        lines.append(c["description"])
        lines.append("")
    lines.append("</corrections>\n")
    return "\n".join(lines)


def get_contextual_mode_prompt(context_payload: dict = None, corrections: list = None) -> str:
    base_prompt = load_prompt("contextual_agent_prompt.txt")
    corrections_block = _build_corrections_block(corrections)

    if context_payload:
        payload_json = json.dumps(context_payload, indent=2)
        context_section = (
            "<external_context>\n"
            "The caller has attached this structured context for the current turn:\n"
            f"{payload_json}\n"
            "</external_context>\n\n"
        )
        return corrections_block + context_section + base_prompt

    return corrections_block + base_prompt
