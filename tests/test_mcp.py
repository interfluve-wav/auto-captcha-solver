"""MCP server protocol tests."""

import sys
import json
from io import StringIO
from auto_captcha_solver.mcp_server import create_server, handle_tool_call

def test_mcp_server_metadata():
    server = create_server()
    assert server["name"] == "auto-captcha"
    assert server["version"].startswith("0.1.")
    assert len(server["tools"]) == 3
    tool_names = [t["name"] for t in server["tools"]]
    assert "captcha_detect" in tool_names
    assert "captcha_solve" in tool_names
    assert "captcha_credits" in tool_names

def test_mcp_tool_schemas():
    server = create_server()
    detect = next(t for t in server["tools"] if t["name"] == "captcha_detect")
    assert detect["inputSchema"]["required"] == ["url"]
    assert "headless" in detect["inputSchema"]["properties"]

def test_mcp_handle_credits(monkeypatch):
    """captcha_credits tool should return a credits dict (no API hit if key missing)."""
    # Without NOPECHA_API_KEY, returns error
    result = handle_tool_call("captcha_credits", {})
    assert "error" in result

def test_mcp_handle_unknown_tool(monkeypatch):
    """Unknown tool should return error message (after API key validation)."""
    monkeypatch.setenv("NOPECHA_API_KEY", "fake-key")
    result = handle_tool_call("nonexistent_tool_xyz", {})
    assert "Unknown tool" in result.get("error", "")

    """Unknown tool should return error message."""
    result = handle_tool_call("nonexistent_tool_xyz", {})
    assert "Unknown tool" in result.get("error", "")

    result = handle_tool_call("unknown_tool", {})
    assert "error" in result
    assert "Unknown tool" in result["error"]
