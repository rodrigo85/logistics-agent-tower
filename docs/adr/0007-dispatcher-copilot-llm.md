# ADR-0007: Dispatcher Copilot - an LLM agent that edits today's plan through tools

* **Status:** Accepted
* **Date:** 2026-09-25

## Context

Dispatchers change the plan in natural language all day long: "we are not
serving customer X today", "customer Y scheduled receiving between 09:00 and
11:00". The planning pipeline (ADR-0001, ADR-0006) is deterministic and has no
interface for such instructions; the LLM settings existed but nothing used them.

## Decision

1. **One conversational agent, not LLM-ified planning.** The Fleet, Routing and
   Risk agents stay deterministic (auditable, testable, fast). The LLM lives in a
   single node, the *copilot*, whose only way to act is through tools.
2. **Tools are the MCP tools.** Operator actions (`find_customers`,
   `skip_customer_today`, `restore_customer_today`, `reschedule_customer_window`,
   `list_orders`, `remember_note`) are plain functions in `mcp/tools.py`,
   registered in the in-process registry, in the stdio MCP server and bound to
   the LLM as LangChain `StructuredTool`s. The copilot adds two orchestration
   tools: `get_plan_summary` and `replan_dispatch`.
3. **Deterministic guard rails around the model:** customer names are resolved by
   the tool with fuzzy matching and an explicit `AMBIGUOUS` outcome (the model must
   ask, never guess); windows are normalised (`8h`, `8:30`, `14 horas`); and if a
   mutating tool succeeded but the model did not call `replan_dispatch`, the
   copilot re-plans anyway. The dashboard and API therefore always reflect the
   plan the operator asked for.
4. **Memory.** Short-term: LangGraph checkpointer per chat `thread_id`.
   Long-term: `operator_memory` (notes, skips, windows) and `customer_rules`
   in SQL, plus `Customer.window_override_*` so a rescheduled window shapes
   future orders; the last entries are injected into the system prompt.
5. **Provider factory** (`llm/provider.py`): Ollama (default, local), Gemini and
   OpenAI behind optional extras; `llm_status()` reports availability without
   exposing secrets; the API answers 503 with the reason when no LLM is usable.
6. **Evaluation harness** (`evals/`): a JSONL case set and a runner that scores
   tool accuracy, entity accuracy, replan correctness and latency per provider
   on a temporary database. Results are written to `evals/results/`.

## Consequences

* The pipeline remains fully usable without any LLM; the copilot is additive.
* Unit tests exercise the real graph, tools and database with a scripted
  tool-calling model; provider quality is measured separately by the evals.
* Every operator action is visible: the API returns the action log, the
  dashboard renders it as chips and the agent log records the tools used.
* Small local models may misroute rare phrasings; the guard rails bound the
  damage to "nothing happened" rather than a wrong mutation.
