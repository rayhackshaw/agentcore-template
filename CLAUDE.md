# agentcore-template — agent orientation

Read this before touching the code. It tells you what this repo *is*, the
invariants you must not break, and the concrete steps to turn this template
into a real product.

## What this is

A Bedrock AgentCore runtime (Strands SDK) implementing **orchestrator +
sub-agents-as-tools**: one streaming `Agent` (the orchestrator) whose tools
are themselves `Agent` instances. Everything is a template/stub — it runs
end-to-end today but answers nothing real until you wire in domain tools and
prompts. There is no git repo yet and no tests.

## Request flow (read top to bottom)

```
payload {prompt, conversationId, sessionInstanceId, mode, contextPayload,
         corrections, userContext}
  -> agent_core/chat/orchestrator.py:main_invoke()   [@main_app.entrypoint]
       - sentinel check: __WARMUP__, __INTERRUPT_REQUEST__,
         __PLAN_APPROVED__:<id> / __PLAN_REJECTED__:<id>
       - modes.get_system_prompt_for_mode(mode, contextPayload, corrections)
       - tools.get_tools_for_mode(mode, has_context_payload)
       - builds Agent(model, system_prompt=[{text},{cachePoint}], tools)
       - agent.stream_async(wrapped_user_message)
  -> orchestrator tools call worker_invoke() (sub_agents/worker_agent.py)
       - acquires a cached or throwaway Agent, streams its own tools
         (example_data_lookup, emit_thinking_step)
       - wraps every raw event in SubAgentResult(agent, event)
  -> orchestrator's stream_async sees SubAgentResult inside tool_stream_event,
     unwraps it, drops raw Bedrock frames, yields domain events upward
  -> consumer (agent_core/run.py SSE, or local_invoke.py CLI, or the real
     AgentCore runtime) gets a flat stream of {"type": ...} dicts terminated
     by {"type": "done"}
```

## File map

| File | Role |
|---|---|
| `agent_core/chat/orchestrator.py` | entrypoint, sentinel handling, stream unwrap/filter |
| `agent_core/chat/modes.py` | mode → system prompt (quick / standard / contextual) |
| `agent_core/chat/tools.py` | mode → tool list |
| `agent_core/sub_agents/worker_agent.py` | agent-as-tool pattern + per-`context_key` agent cache |
| `agent_core/tools/example_tool.py` | **stub** — replace with real data/API integration |
| `agent_core/tools/clarification_tool.py` | clickable clarification options + plan-approval LRU |
| `agent_core/tools/interrupt_checker.py` | mid-task interrupt check tool |
| `agent_core/utils/interrupt_manager.py` | `conversation_id -> threading.Event` registry |
| `agent_core/utils/interrupt_hook.py` | `BeforeToolCallEvent` hook, cancels next tool call |
| `agent_core/utils/prompt_loader.py` | loads `prompts/*.txt`, injects `<current_date_context>` |
| `agent_core/utils/sub_agent_result.py` | `SubAgentResult` wrapper + metadata stripping |
| `agent_core/run.py` | FastAPI SSE server mimicking the real AgentCore invoke contract |
| `agent_core/local_invoke.py` | CLI pretty-printer, no HTTP |
| `prompts/*.txt` | placeholder system prompts — edit here, not in code |

## Invariants — do not break these

1. **Prompt caching is mandatory.** Every `BedrockModel` needs
   `cache_config=CacheConfig(tools_ttl=True)`, and every `system_prompt` list
   must end with `{"cachePoint": {"type": "default"}}`. Omitting it multiplies
   Bedrock cost ~10x on multi-turn conversations.
2. **Never forward raw Bedrock/Strands frames.** A dict with an `"event"` key
   is a raw frame (`contentBlockDelta`, `messageStop`, ...) from a sub-agent's
   own stream — `_is_raw_bedrock_frame` must keep dropping these, or
   downstream consumers duplicate text and flush buffers early.
3. **Every new event `type` string needs a consumer-side whitelist entry.**
   There is no schema enforcement — an unlisted type is silently dropped, not
   an error. Keep `local_invoke.py:_print_event` and your real frontend in
   sync with any new type you add.
4. **Sentinels aren't real user turns.** `__PLAN_APPROVED__:<id>` /
   `__PLAN_REJECTED__:<id>` rewrite into a natural-language resume
   instruction server-side; never fabricate a fake "Yes, proceed" user
   message — it corrupts the transcript the model sees.
5. **Interrupts are process-level, not per-Agent.** `__INTERRUPT_REQUEST__`
   arrives as a *separate* invocation from the one being cancelled, so the
   flag in `interrupt_hook.py` is a module global, not agent state. After an
   interrupt, the caller must mint a new `sessionInstanceId` for the next
   turn (AgentCore keys session state on that id).
6. **Sub-agent concurrency.** `worker_agent._acquire_worker_agent` caches one
   `Agent` per `context_key` so sequential calls keep history; a *concurrent*
   call on a busy key gets a throwaway agent — Strands raises
   `ConcurrencyException` on a second simultaneous `stream_async` for the same
   Agent, so don't "fix" this by removing the busy-check.

## What's a stub vs. what's load-bearing

Stub (safe/expected to replace):
- `agent_core/tools/example_tool.py` — fake data lookup, zero rows every time.
- `prompts/*.txt` — four files, each literally say "Replace this file with
  your product's actual instructions."
- `agent_core/chat/tools.py:get_contextual_tools()` — returns `[]`, an
  extension point for context-only tools.

Load-bearing (keep the shape even if you change the internals):
- The `thinking` → `tool_query` → `tool_result` event sequence any
  domain tool emits (see `example_tool.py`) — downstream code expects this
  shape.
- `SubAgentResult(agent, event)` as the wrapper every sub-agent/tool yields.
- The sentinel strings (`__WARMUP__`, `__INTERRUPT_REQUEST__`,
  `__PLAN_APPROVED__:`/`__PLAN_REJECTED__:`).

## How to implement a real product on this template

1. **Validate model IDs** in `.env` against your AWS account/region —
   `ORCHESTRATOR_MODEL_ID` / `WORKER_MODEL_ID` in `.env.example` are
   placeholders, not a guarantee (check via `list-foundation-models` /
   `list-inference-profiles`).
2. **Write the real prompts.** Fill in all four `prompts/*.txt` files with
   actual domain instructions. Keep the structural pieces each already
   documents (clarification-before-ambiguous-work, plan-approval for
   multi-step tasks, interrupt-checking for long tasks) unless your product
   doesn't need them.
3. **Replace `example_tool.py`** with your real integration (SQL, REST,
   vector search, whatever backs the product). Keep the
   `thinking → tool_query → tool_result` event shape so nothing downstream
   has to change; swap the body, not the contract. Register it on the
   worker agent's `tools=[...]` list in `worker_agent.py`.
4. **Decide if you need more sub-agents.** The template ships one generic
   `worker_agent`. If your domain needs distinct specialists (e.g. a
   SQL agent and a doc-search agent), copy `worker_agent.py`'s shape: a
   module-level `BedrockModel` + cached `Agent`s, an `@tool async def`
   generator wrapping `SubAgentResult`, an `InterruptHook`. Register each as
   a tool in `chat/tools.py`.
5. **Decide if you need `contextual` mode at all.** It exists to show how to
   inline an arbitrary external payload (e.g. "the record the user is
   currently viewing") into the prompt via `<external_context>`. If your
   product has no such notion, delete the mode, its prompt file, and the
   `contextPayload` plumbing in `orchestrator.py`/`modes.py`/`tools.py`.
6. **Extend the event contract deliberately.** If a new tool needs a new
   event `type`, add it to the whitelist wherever the stream is consumed
   (today: `local_invoke.py`; in production: your real frontend/backend) —
   see invariant 3.
7. **Test locally** with `uv run agentcore-invoke "<prompt>" --mode standard`
   (CLI) or `uv run agentcore-local` (SSE server on `:8080`,
   `POST /invocations`) before deploying to a real AgentCore runtime.
8. **Decide on plan-approval UX.** `ask_clarification(..., plan=...)` stores
   plan text in an in-memory LRU (`clarification_tool.py`, max 64, not
   persisted) — fine for a single-process dev/staging runtime, but if you run
   multiple AgentCore instances behind a load balancer, this LRU needs to
   move to shared storage (Redis, DynamoDB) or plan approval will fail when
   the approve/reject sentinel lands on a different instance than the one
   that stored the plan.

## Local dev commands

```bash
cp .env.example .env   # fill in model IDs / region
uv sync
uv run agentcore-invoke "hello, what can you do?" --mode standard
uv run agentcore-local   # HTTP harness, POST /invocations, SSE
```
