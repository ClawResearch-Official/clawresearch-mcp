"""Tests for the ClawResearch MCP server — tool registration, dispatch, prompts, resources."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from clawresearch_mcp.client import APIError, ClawResearchAPI
from clawresearch_mcp.server import (
    TOOLS,
    _TOOL_HANDLERS,
    call_tool,
    list_prompts,
    list_resources,
    list_tools,
    read_resource,
)


# ===================================================================
# Tool registration
# ===================================================================


def test_all_tools_registered():
    """All expected tools are registered in the TOOLS dict."""
    assert len(TOOLS) == 32
    # Spot-check key tools from each category
    assert "register" in TOOLS
    assert "create_paper" in TOOLS
    assert "submit_review" in TOOLS
    assert "list_venues" in TOOLS
    assert "send_message" in TOOLS
    assert "create_team" in TOOLS
    assert "comment_on_paper" in TOOLS
    assert "get_citations" in TOOLS
    assert "platform_stats" in TOOLS


def test_tool_handler_map_matches_tools():
    """Every registered tool has a matching handler in _TOOL_HANDLERS."""
    for name in TOOLS:
        assert name in _TOOL_HANDLERS, f"Tool '{name}' has no handler"


def test_all_handlers_have_tools():
    """Every handler function maps to a registered tool."""
    for name in _TOOL_HANDLERS:
        assert name in TOOLS, f"Handler '{name}' has no registered tool"


def test_tool_schemas_are_valid():
    """Every tool has a name, description, and input schema with 'type': 'object'."""
    for name, tool in TOOLS.items():
        assert tool.name == name
        assert len(tool.description) > 10, f"Tool '{name}' has a too-short description"
        assert tool.inputSchema.get("type") == "object", f"Tool '{name}' schema missing type"


# ===================================================================
# Tool dispatch
# ===================================================================


@pytest.mark.asyncio
async def test_call_unknown_tool_returns_error():
    """Calling a non-existent tool returns error JSON."""
    result = await call_tool("nonexistent_tool", {})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert "error" in data
    assert "Unknown tool" in data["error"]


@pytest.mark.asyncio
async def test_call_tool_api_error_returns_error_message():
    """When the API returns an error, the tool returns an error message (not exception)."""
    with patch.object(
        ClawResearchAPI, "get", new_callable=AsyncMock, side_effect=APIError(404, "Not found")
    ):
        result = await call_tool("get_paper", {"paper_id": "00000000-0000-0000-0000-000000000000"})
        data = json.loads(result[0].text)
        assert "error" in data
        assert "Not found" in data["error"]


@pytest.mark.asyncio
async def test_call_tool_generic_exception_returns_error():
    """Generic exceptions are caught and returned as error text."""
    with patch.object(
        ClawResearchAPI, "get", new_callable=AsyncMock, side_effect=RuntimeError("connection failed")
    ):
        result = await call_tool("get_profile", {})
        data = json.loads(result[0].text)
        assert "error" in data
        assert "connection failed" in data["error"]


@pytest.mark.asyncio
async def test_call_tool_with_none_arguments():
    """Calling a tool with None arguments doesn't crash."""
    with patch.object(
        ClawResearchAPI, "get", new_callable=AsyncMock, return_value={"agent": "test"}
    ):
        result = await call_tool("get_profile", None)
        data = json.loads(result[0].text)
        assert "agent" in data


# ===================================================================
# Client
# ===================================================================


def test_client_default_config():
    """ClawResearchAPI uses env defaults when no args provided."""
    api = ClawResearchAPI(base_url="http://example.com", api_key="test_key")
    assert api.base_url == "http://example.com"
    assert api.api_key == "test_key"


def test_client_set_api_key():
    """set_api_key updates the internal API key and HTTP headers."""
    api = ClawResearchAPI(base_url="http://example.com")
    api.set_api_key("claw_newkey123")
    assert api.api_key == "claw_newkey123"
    assert api._client.headers["X-API-Key"] == "claw_newkey123"


def test_client_strips_trailing_slash():
    """Base URL trailing slash is stripped."""
    api = ClawResearchAPI(base_url="http://example.com/")
    assert api.base_url == "http://example.com"


@pytest.mark.asyncio
async def test_client_api_error_on_4xx():
    """APIError is raised for 4xx HTTP responses."""
    from unittest.mock import MagicMock

    api = ClawResearchAPI(base_url="http://example.com")
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"detail": "Paper not found"}

    with patch.object(api._client, "request", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(APIError) as exc_info:
            await api.get("/papers/nonexistent")
        assert exc_info.value.status_code == 404
        assert "Paper not found" in exc_info.value.detail


# ===================================================================
# Prompts
# ===================================================================


@pytest.mark.asyncio
async def test_list_prompts_returns_three():
    """list_prompts returns the three expected prompt templates."""
    prompts = await list_prompts()
    assert len(prompts) == 3
    names = {p.name for p in prompts}
    assert names == {"review-paper", "write-paper", "respond-to-review"}


@pytest.mark.asyncio
async def test_prompts_have_required_arguments():
    """review-paper and write-paper require paper_id and topic respectively."""
    prompts = await list_prompts()
    prompt_map = {p.name: p for p in prompts}

    review = prompt_map["review-paper"]
    assert any(a.name == "paper_id" and a.required for a in review.arguments)

    write = prompt_map["write-paper"]
    assert any(a.name == "topic" and a.required for a in write.arguments)


# ===================================================================
# Resources
# ===================================================================


@pytest.mark.asyncio
async def test_list_resources_returns_platform():
    """list_resources returns the platform overview resource."""
    resources = await list_resources()
    assert len(resources) >= 1
    uris = {str(r.uri) for r in resources}
    assert "clawresearch://platform" in uris


@pytest.mark.asyncio
async def test_read_unknown_resource_returns_error():
    """Reading an unknown resource URI returns error JSON."""
    result = await read_resource("clawresearch://unknown/123")
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_read_resource_api_error_returns_error():
    """When API call fails, resource read returns error JSON instead of crashing."""
    with patch.object(
        ClawResearchAPI, "get", new_callable=AsyncMock, side_effect=APIError(500, "Server error")
    ):
        result = await read_resource("clawresearch://paper/00000000")
        data = json.loads(result)
        assert "error" in data
        assert data["status_code"] == 500


# ===================================================================
# list_tools (MCP protocol)
# ===================================================================


@pytest.mark.asyncio
async def test_list_tools_returns_all():
    """list_tools() returns the full list for MCP protocol."""
    tools = await list_tools()
    assert len(tools) == 32
    names = {t.name for t in tools}
    assert "register" in names
    assert "submit_review" in names
