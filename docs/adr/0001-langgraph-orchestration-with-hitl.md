# ADR-0001: LangGraph for agent orchestration with a Human-in-the-Loop interrupt

* **Status:** Accepted
* **Date:** 2026-09-24

## Context

Dispatch planning is a pipeline of specialised steps (allocate loads, sequence
routes, audit risk, finalise) that must be able to **pause** for a human decision
and **resume** later from the exact same state, possibly from a different HTTP
request. We also want a structure that can later host LLM-backed nodes without
rewriting the pipeline.

## Decision

Model the pipeline as a LangGraph `StateGraph` over a `TypedDict` state.
Specialist agents are plain Python node functions. The HITL gate uses
`langgraph.types.interrupt()`; execution state is persisted by a checkpointer
(`MemorySaver` locally) and resumed with `Command(resume=...)`.

## Consequences

* Pause/resume across requests works out of the box; the API only needs a
  `thread_id`.
* Nodes are deterministic today. An LLM node (e.g. explaining risks to the
  dispatcher, or negotiating windows) can be added as one more node without
  touching the others. `LLM_PROVIDER` settings are reserved for that.
* `MemorySaver` ties the process to a single instance. Scaling horizontally
  requires `PostgresSaver` (langgraph-checkpoint-postgres) pointing at the same
  database; the change is confined to `memory/short_term.py`.
* We take on a dependency on LangGraph's API stability (>= 1.2).
