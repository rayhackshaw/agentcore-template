from pathlib import Path
from datetime import datetime
from .logging import logger

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def get_date_context() -> str:
    """Current-date block prepended to prompts so models don't reason about
    "this year" / "recent" using their training cutoff."""
    now = datetime.now()
    return f"""<current_date_context>
**CRITICAL: CURRENT DATE INFORMATION**

Today's date: {now.strftime('%Y-%m-%d')} ({now.strftime('%A, %d %B %Y')})
Current year: {now.year}
Current month: {now.strftime('%B %Y')}

When the user says "this year", "current", or "recent", they mean {now.year}.
When they say "last year" or "previous", they mean {now.year - 1}.

**DO NOT assume or infer dates from training data. Use the current date provided above.**
</current_date_context>

"""


def load_prompt(filename: str, inject_date_context: bool = True) -> str:
    """Load a prompt from PROMPTS_DIR, optionally prepending the date context block."""
    try:
        with open(PROMPTS_DIR / filename, "r", encoding="utf-8") as f:
            prompt_content = f.read()

        if inject_date_context:
            prompt_content = get_date_context() + prompt_content

        return prompt_content
    except FileNotFoundError:
        logger.error(f"Prompt file not found at {PROMPTS_DIR / filename}")
        return ""
    except Exception as e:
        logger.error(f"Error loading prompt file {filename}: {e}")
        return ""
