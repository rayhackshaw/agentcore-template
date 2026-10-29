"""
Local development server. Wraps main_invoke() in a FastAPI SSE endpoint that
mimics the Bedrock AgentCore runtime invoke contract, so a downstream service
can target this the same way it would target a deployed runtime ARN.

Usage:
    cd agentcore && uv run agentcore-local
"""

import json
import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from agent_core.chat.orchestrator import main_invoke

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent_core_local")

app = FastAPI(title="agentcore local runtime")


@app.post("/invocations")
async def invocations(request: Request):
    payload = await request.json()
    logger.info(f"[LOCAL] /invocations  mode={payload.get('mode', 'standard')}  prompt={str(payload.get('prompt', ''))[:120]}")

    async def event_stream():
        try:
            async for event in main_invoke(payload):
                if not isinstance(event, dict):
                    continue
                try:
                    yield f"data: {json.dumps(event)}\n\n"
                except (TypeError, ValueError):
                    logger.debug(f"[LOCAL] Skipping non-serialisable event: {type(event).__name__}")
        except Exception as exc:
            logger.exception("[LOCAL] Error during invocation")
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


def run_local_server():
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
