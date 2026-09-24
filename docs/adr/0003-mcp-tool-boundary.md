# ADR-0003: Model Context Protocol as the tool boundary between agents and WMS/TMS

* **Status:** Accepted
* **Date:** 2026-09-24

## Context

Agents need to read orders and fleet, ask for a route and confirm a manifest.
Calling services directly from agent code couples orchestration to persistence
and makes it impossible to expose the same capabilities to external AI clients
(IDE assistants, chat operators, other agents).

## Decision

Define every capability once as a plain function in `mcp/tools.py`, then expose
it twice:

1. **In-process** through `MCPToolClient` (`mcp/client.py`), used by the graph
   nodes. No network hop, fully testable.
2. **Over the wire** through an MCP server (`mcp/server.py`, stdio transport),
   registering the same functions as MCP tools and resources
   (`wms://orders/summary`, `tms://fleet/summary`).

## Consequences

* Agents depend on tool names and JSON-shaped results, not on SQLAlchemy.
* The tool registry doubles as documentation: `GET /mcp/tools` lists it.
* The MCP server needs the optional `mcp` extra; it is not part of the unit
  suite and is verified manually with an MCP-capable client.
