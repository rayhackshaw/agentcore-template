# agentcore

> This is a personal template for getting started with Bedrock AgentCore. It
> collects patterns I've found useful in my own agent projects, so you can
> skip the trial-and-error and build on something that already works.

A Bedrock AgentCore runtime built on [Strands](https://strandsagents.com) that
implements an orchestrator + sub-agents-as-tools pattern: one orchestrator
agent picks tools, and those tools are themselves streaming sub-agents. Use
this as a starting point for a new agent product.

## Directory map

| Path | Purpose |
|---|---|
| `agent_core/chat/` | Entrypoint, plus mode → prompt/tool mappings |
| `agent_core/sub_agents/worker_agent.py` | The agent-as-tool pattern |
| `agent_core/tools/` | Tools the agents can call — clarification, interrupt checks, the example data stub |
| `agent_core/utils/` | Shared plumbing: interrupts, prompt loading, event wrapping |
| `agent_core/run.py` | Local FastAPI SSE server |
| `agent_core/local_invoke.py` | CLI for testing without any server |
| `prompts/*.txt` | System prompts, kept as plain text so you edit them without touching code |

## How it works

- **Orchestrator + sub-agents.** One main agent handles the conversation and
  calls sub-agents as tools when it needs to do real work. Each sub-agent's
  stream rides back through the orchestrator's, so the end user still sees
  one continuous response.
- **Control flow via sentinels.** Warmup pings, interrupt requests, and
  plan approve/reject all arrive as special string messages rather than a
  separate API — keeps the whole thing to one entrypoint.
- **Prompt caching is on by default.** Every model call and system prompt is
  set up to cache — skipping this makes repeated calls dramatically more
  expensive, so don't remove it.
- **Interrupts work mid-task.** A user can cancel a long-running request;
  sub-agents can also check in periodically so cancellation doesn't wait for
  the next step boundary.
- **Prompts are files, not code.** Editing `prompts/*.txt` is the main way
  you'll customize behavior — no redeploy-the-logic needed.

One thing to keep in mind: whatever reads this agent's output stream needs to
know about every event `type` it can produce, or new event types get
silently dropped. Keep that in sync as you add tools.

## Local dev

```bash
cp .env.example .env   # fill in your model IDs / region
uv sync
uv run agentcore-invoke "hello, what can you do?" --mode standard
# or, to run the HTTP harness another service can hit:
uv run agentcore-local
```

`agentcore-local` boots a FastAPI server on `:8080` with a single
`POST /invocations` endpoint that mirrors the shape a real AgentCore runtime
exposes (SSE stream of JSON events, terminated by `{"type": "done"}`).

## Before you deploy this for real

- **Validate model IDs against your account** via `list-foundation-models` /
  `list-inference-profiles` — the defaults in `.env.example` are placeholders,
  not a guarantee they exist in your region/account.
- Swap `agent_core/tools/example_tool.py` for your real data/API integration,
  keeping the `thinking` → `tool_query` → `tool_result` event shape so
  nothing downstream has to change.
- Fill in `prompts/*.txt` with your actual domain instructions — they're
  intentionally skeletal placeholders right now.
- Decide whether you need the `contextual` mode at all — it exists to show
  how to inline an arbitrary external payload into the prompt.

## Acknowledgements / caveats

- **Model provider differences.** Response structure (streaming events, tool
  call shapes, etc.) differs between providers — Anthropic vs. OpenAI, for
  example. Switching providers will likely mean adjusting how Strands
  responses are handled here. Play this by ear.
- **AgentCore Harnesses are untested.** This template assumes plain AgentCore
  Runtimes, not the Harness layer — I haven't experimented with that yet.
- **The interrupt mechanism is old and somewhat destructive.** It cancels a
  session and effectively rebuilds it to handle the interrupt, rather than
  pausing and resuming cleanly. A newer agent SDK (e.g. the Vercel AI SDK)
  would give you more intuitive, fine-grained control over interrupts.
