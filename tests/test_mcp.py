"""Tests for the Model Context Protocol tools, the in-process client and the stdio server definition."""

import asyncio

import pytest

from logistics_tower.config import settings
from logistics_tower.mcp.client import get_mcp_client

EXPECTED_TOOLS = {
    "get_pending_orders",
    "get_available_fleet",
    "get_customer_dock_rules",
    "optimize_vehicle_route",
    "confirm_dispatch_manifest",
    "find_customers",
    "skip_customer_today",
    "restore_customer_today",
    "reschedule_customer_window",
    "list_orders",
    "remember_note",
}


def test_mcp_client_tool_listing():
    names = {t["name"] for t in get_mcp_client().list_tools()}
    assert names >= EXPECTED_TOOLS


def test_mcp_client_tool_execution():
    client = get_mcp_client()
    orders = client.call_tool("get_pending_orders", cd_id=settings.default_cd_id)
    assert isinstance(orders, list) and len(orders) == 40

    fleet = client.call_tool("get_available_fleet", cd_id=settings.default_cd_id)
    assert len(fleet) == 5

    plan = client.call_tool("optimize_vehicle_route", orders=orders[:3])
    assert len(plan["stops"]) == 3 and plan["itinerary"]

    with pytest.raises(ValueError):
        client.call_tool("does_not_exist")


def test_mcp_server_exposes_the_same_tools_over_the_protocol():
    """The stdio server (official `mcp` SDK) must register every tool of the in-process registry."""
    mcp = pytest.importorskip("mcp")
    assert mcp is not None
    from logistics_tower.mcp.server import mcp_server

    list_tools = getattr(mcp_server, "list_tools", None)
    if list_tools is None:
        pytest.skip("MCP SDK does not expose list_tools() on the server object")
    result = list_tools()
    tools = asyncio.run(result) if asyncio.iscoroutine(result) else result
    names = {t.name for t in tools}
    assert names >= EXPECTED_TOOLS
