"""
Stub for a domain data/API integration (SQL, REST, vector search, whatever
backs your product). Swap the body for a real call but keep the
thinking -> tool_query -> tool_result event shape — that's the contract the
rest of the pipeline (and whatever backend forwards this stream onward)
expects.
"""

from typing import AsyncIterator

from strands import tool

from agent_core.utils import SubAgentResult, get_agent_logger

logger = get_agent_logger("example_tool")


@tool
async def example_data_lookup(query: str) -> AsyncIterator:
    """
    Stub data lookup. Replace with a real integration.

    Args:
        query: Natural-language or structured query to run against your data source.
    """
    logger.info(f"[EXAMPLE_TOOL] query={query!r}")

    yield SubAgentResult(
        agent="example_tool",
        event={"type": "thinking", "content": f"Looking up: {query}"},
    )

    yield SubAgentResult(
        agent="example_tool",
        event={"type": "tool_query", "query": query},
    )

    yield SubAgentResult(
        agent="example_tool",
        event={"type": "tool_result", "columns": [], "rows": [], "total_rows": 0},
    )

    yield "No data source wired up yet — replace example_data_lookup with a real integration."
