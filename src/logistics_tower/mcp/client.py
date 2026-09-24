"""
MCP Client Adapter for LangChain and LangGraph Agents.
Bridges MCP Server tool executions into native agent tool-call structures.
"""

import json
import logging
from typing import Any, Callable, Dict, List

from logistics_tower.mcp.tools import (
    tool_confirm_dispatch,
    tool_get_available_fleet,
    tool_get_customer_dock_rules,
    tool_get_pending_orders,
    tool_optimize_route,
)

logger = logging.getLogger(__name__)


class MCPToolClient:
    """
    Client adapter facilitating tool discovery, schema introspection,
    and invocation across the MCP boundary for autonomous agents.
    """

    def __init__(self):
        self._tools: Dict[str, Callable[..., Any]] = {
            "get_pending_orders": tool_get_pending_orders,
            "get_available_fleet": tool_get_available_fleet,
            "get_customer_dock_rules": tool_get_customer_dock_rules,
            "optimize_vehicle_route": tool_optimize_route,
            "confirm_dispatch_manifest": tool_confirm_dispatch,
        }

    def list_tools(self) -> List[Dict[str, str]]:
        return [
            {"name": name, "description": func.__doc__ or ""}
            for name, func in self._tools.items()
        ]

    def call_tool(self, tool_name: str, **kwargs) -> Any:
        if tool_name not in self._tools:
            raise ValueError(f"Tool {tool_name} not found in MCP registry.")
        logger.info(f"MCP Client: Invoking {tool_name} with params {kwargs}")
        return self._tools[tool_name](**kwargs)


_mcp_client = MCPToolClient()


def get_mcp_client() -> MCPToolClient:
    return _mcp_client
