# Architecture Decision Records

Short, dated records of decisions that are expensive to reverse. Format follows
[Michael Nygard's template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

| ID | Title | Status |
|----|-------|--------|
| [0001](0001-langgraph-orchestration-with-hitl.md) | LangGraph for agent orchestration with a Human-in-the-Loop interrupt | Accepted |
| [0002](0002-or-tools-for-routing.md) | Google OR-Tools as the routing engine | Accepted |
| [0003](0003-mcp-tool-boundary.md) | Model Context Protocol as the tool boundary between agents and WMS/TMS | Accepted |
| [0004](0004-dedicated-ftl-multi-trip.md) | Dedicated full-truckload, multi-trip allocation model | Superseded by 0006 |
| [0005](0005-sqlalchemy-sqlite-postgres.md) | SQLAlchemy 2.0 with SQLite locally and PostgreSQL in production | Accepted |
| [0006](0006-refrigerated-multi-drop-single-route.md) | Refrigerated multi-drop routes, one route per vehicle per day | Accepted |

To add one: copy the newest file, bump the number, set status *Proposed*, open a PR.
