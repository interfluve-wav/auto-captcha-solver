#!/usr/bin/env python3
"""
auto-captcha MCP Server — exposes captcha solving as MCP tools.

Any MCP-compatible agent (Claude Code, OpenClaw, Cursor, etc.) can use this
to solve captchas during browser automation.

Usage:
    # With Claude Code
    claude mcp add auto-captcha -- python -m auto_captcha.mcp_server

    # Or in MCP config
    {
      "mcpServers": {
        "auto-captcha": {
          "command": "python",
          "args": ["-m", "auto_captcha.mcp_server"],
          "env": {"NOPECHA_API_KEY": "your-key"}
        }
      }
    }
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

# MCP server using stdio transport
# Implements the MCP protocol for tool discovery and execution
from auto_captcha_solver.providers import resolve_api_key
from auto_captcha_solver.types import sanitize_detect_results


def _build_solver(arguments: dict[str, Any]) -> tuple[Any | None, dict[str, Any] | None]:
    from auto_captcha_solver import CaptchaSolver

    provider = os.environ.get("CAPTCHA_PROVIDER", "nopecha")
    api_key = resolve_api_key(provider)
    if not api_key:
        return None, {
            "error": (
                f"API key not set for provider '{provider}'. "
                "Set NOPECHA_API_KEY or CAPTCHAAI_API_KEY."
            )
        }
    timeout = arguments.get("timeout")
    solver = CaptchaSolver(api_key=api_key, provider=provider)
    if timeout is not None:
        solver.timeout_sec = float(timeout)
    return solver, None


def create_server() -> dict[str, Any]:
    """Create and return the MCP server definition."""
    return {
        "name": "auto-captcha",
        "version": "0.1.0",
        "tools": [
            {
                "name": "captcha_detect",
                "description": "Detect captchas on a Playwright page. Call this when browser automation encounters a captcha.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of the page with the captcha",
                        },
                        "headless": {
                            "type": "boolean",
                            "default": True,
                            "description": "Run browser headless",
                        },
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "captcha_solve",
                "description": "Detect and solve all captchas on a page. Returns solved tokens that can be used to bypass the captcha.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of the page with the captcha",
                        },
                        "headless": {
                            "type": "boolean",
                            "default": True,
                            "description": "Run browser headless",
                        },
                        "timeout": {
                            "type": "number",
                            "default": 120,
                            "description": "Solve timeout in seconds",
                        },
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "captcha_credits",
                "description": "Check remaining API credits for the configured provider.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ],
    }


def handle_tool_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool and return the result."""
    from auto_captcha_solver import CaptchaSolver

    solver, err = _build_solver(arguments)
    if err is not None:
        return err
    if not isinstance(solver, CaptchaSolver):
        return {"error": "solver initialization failed"}

    if tool_name == "captcha_credits":
        return {"provider": solver.provider, "credits": solver.get_credits()}

    if tool_name == "captcha_detect":
        url = arguments["url"]
        headless = arguments.get("headless", True)

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(url, timeout=30000)
            time.sleep(3)
            captchas = sanitize_detect_results(solver.detect(page))
            browser.close()

        return {"captchas": captchas, "count": len(captchas)}

    if tool_name == "captcha_solve":
        url = arguments["url"]
        headless = arguments.get("headless", True)

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(url, timeout=30000)
            time.sleep(3)
            results = solver.auto_solve(page)
            browser.close()

        output = []
        for r in results:
            output.append(
                {
                    "type": r.captcha_type,
                    "success": r.success,
                    "token": r.token,
                    "error": r.error,
                    "attempts": r.attempts,
                    "elapsed_sec": r.elapsed_sec,
                }
            )
        return {"results": output}

    return {"error": f"Unknown tool: {tool_name}"}


def run_stdio_server() -> None:
    """Run as a stdio MCP server."""
    server_info = create_server()

    while True:
        request_id: Any = None
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line.strip())
            method = request.get("method")
            request_id = request.get("id")

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": server_info["name"],
                            "version": server_info["version"],
                        },
                    },
                }

            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": server_info["tools"]},
                }

            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = handle_tool_call(tool_name, arguments)
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
                }

            elif method == "notifications/initialized":
                continue  # No response needed for notifications

            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError:
            continue
        except Exception as e:
            if request_id:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32603, "message": str(e)},
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
