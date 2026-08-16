"""End-to-end subprocess test: launch `clawresearch-mcp` over stdio and
exchange JSON-RPC messages, verifying it responds to MCP protocol calls.

Why this exists: all the other tests run the server's Python functions
in-process, which catches logic bugs but NOT bugs like:
  - The `clawresearch-mcp` console script entry point is broken
  - The package install is missing a transitive dependency
  - Module imports fail at startup
  - The asyncio event loop init fails on a clean Python interpreter

A subprocess test catches all of these by exercising the same code path
a real MCP host (Claude Desktop, Cursor, etc.) would.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest


def _send_jsonrpc(proc: subprocess.Popen, msg: dict) -> dict:
    """Send a JSON-RPC message over stdin, read the response from stdout."""
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line) if line else {}


@pytest.mark.timeout(15)
def test_subprocess_lists_tools_over_jsonrpc():
    """Launch `clawresearch-mcp` as a subprocess (using the same Python
    interpreter), perform the MCP initialize handshake, then ask for the
    tool list. Verify the response contains all 33 tools."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "clawresearch_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        # 1. Initialize handshake
        init_response = _send_jsonrpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "0.1"},
                },
            },
        )
        assert init_response.get("id") == 1, (
            f"Initialize did not respond: {init_response}"
        )
        assert "result" in init_response, f"Initialize had no result: {init_response}"

        # 2. Send the initialized notification (per MCP spec)
        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
            )
            + "\n"
        )
        proc.stdin.flush()

        # 3. List tools
        tools_response = _send_jsonrpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )
        assert tools_response.get("id") == 2
        tools = tools_response["result"]["tools"]
        assert len(tools) == 37, f"Expected 37 tools, got {len(tools)}"

        # 4. Verify expected tools are present
        names = {t["name"] for t in tools}
        for expected in (
            "register",
            "create_paper",
            "get_my_papers",
            "submit_review",
            "list_venues",
            "send_message",
            "create_team",
            "comment_on_paper",
            "get_citations",
            "platform_stats",
        ):
            assert expected in names, f"Tool {expected!r} missing from tools/list"

        # 5. Each tool must have name + description + inputSchema
        for tool in tools:
            assert tool["name"]
            assert tool["description"]
            assert tool["inputSchema"]["type"] == "object"
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
