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

import json
import os
import sys

# MCP server using stdio transport
# Implements the MCP protocol for tool discovery and execution


def create_server():
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
                "description": "Check remaining NopeCHA API credits.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ],
    }


def handle_tool_call(tool_name: str, arguments: dict) -> dict:
    """Execute a tool and return the result."""
    api_key = os.environ.get("NOPECHA_API_KEY", "")
    if not api_key:
        return {"error": "NOPECHA_API_KEY environment variable not set"}

    from auto_captcha import CaptchaSolver

    solver = CaptchaSolver(api_key=api_key)

    if tool_name == "captcha_credits":
        return {"credits": solver.get_credits()}

    elif tool_name == "captcha_detect":
        url = arguments["url"]
        headless = arguments.get("headless", True)

        from playwright.sync_api import sync_playwright
        import time

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(url, timeout=30000)
            time.sleep(3)
            captchas = solver.detect(page)
            browser.close()

        return {"captchas": captchas, "count": len(captchas)}

    elif tool_name == "captcha_solve":
        url = arguments["url"]
        headless = arguments.get("headless", True)

        from playwright.sync_api import sync_playwright
        import time

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(url, timeout=30000)
            time.sleep(3)
            results = solver.auto_solve(page)
            browser.close()

        output = []
        for r in results:
            output.append({
                "type": r.captcha_type,
                "success": r.success,
                "token": r.token,
                "error": r.error,
                "attempts": r.attempts,
                "elapsed_sec": r.elapsed_sec,
            })
        return {"results": output}

    return {"error": f"Unknown tool: {tool_name}"}


def run_stdio_server():
    """Run as a stdio MCP server."""
    import json

    server_info = create_server()

    while True:
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
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                    },
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
