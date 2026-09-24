"""Unit tests for Model Context Protocol (MCP) tools and client."""

from logistics_tower.mcp.client import get_mcp_client


def test_mcp_client_tool_listing():
    client = get_mcp_client()
    tools = client.list_tools()
    tool_names = [t["name"] for t in tools]

    assert "get_pending_orders" in tool_names
    assert "get_available_fleet" in tool_names
    assert "optimize_vehicle_route" in tool_names
    assert "confirm_dispatch_manifest" in tool_names


def test_mcp_client_tool_execution():
    client = get_mcp_client()
    orders = client.call_tool("get_pending_orders", cd_id="CD-ITAJAI-SC01")
    assert isinstance(orders, list)
    assert len(orders) > 0

    fleet = client.call_tool("get_available_fleet", cd_id="CD-ITAJAI-SC01")
    assert isinstance(fleet, list)
    assert len(fleet) > 0
