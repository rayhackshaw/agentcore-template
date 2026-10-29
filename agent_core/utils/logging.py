import logging
import sys
import os
from pathlib import Path

if os.getenv("ENVIRONMENT") == "production" or not os.access(".", os.W_OK):
    log_path = Path("/tmp/agentcore.log")
else:
    package_root = Path(__file__).parent.parent.parent
    log_path = package_root / "agentcore.log"

handlers = [logging.StreamHandler(sys.stdout)]

try:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers.append(logging.FileHandler(str(log_path), mode="a", encoding="utf-8"))
except (PermissionError, OSError) as e:
    sys.stderr.write(f"Warning: Cannot create log file at {log_path}: {e}\nLogging to stdout only\n")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=handlers,
)

for _noisy in (
    "botocore",
    "boto3",
    "urllib3",
    "httpx",
    "httpcore",
    "strands",
    "bedrock_agentcore",
    "asyncio",
    "opentelemetry",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def get_agent_logger(agent_name: str) -> logging.Logger:
    return logging.getLogger(f"agent_core.{agent_name}")


def _sanitize_for_logging(content: str) -> str:
    try:
        content.encode("utf-8")
        return content
    except UnicodeEncodeError:
        return "".join(
            char if ord(char) < 128 else f"[U+{ord(char):04X}]" for char in content
        )


def log_agent_message(logger: logging.Logger, agent_name: str, message_type: str, content: str):
    safe_content = _sanitize_for_logging(str(content))
    logger.info(f"[{agent_name.upper()}] {message_type}: {safe_content}")


_LOG_ARG_PREVIEW_CHARS = 100


def log_function_call(logger: logging.Logger, agent_name: str, function_name: str, args: dict = None):
    if args:
        preview = _sanitize_for_logging(str(args))
        if len(preview) > _LOG_ARG_PREVIEW_CHARS:
            preview = preview[:_LOG_ARG_PREVIEW_CHARS] + "…"
        logger.info(f"[{agent_name.upper()}]: invoked {function_name} with args {preview}")
    else:
        logger.info(f"[{agent_name.upper()}]: invoked {function_name}")
