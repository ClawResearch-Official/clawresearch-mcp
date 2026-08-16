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
    assert len(TOOLS) == 37
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
        assert tool.inputSchema.get("type") == "object", (
            f"Tool '{name}' schema missing type"
        )


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
        ClawResearchAPI,
        "get",
        new_callable=AsyncMock,
        side_effect=APIError(404, "Not found"),
    ):
        result = await call_tool(
            "get_paper", {"paper_id": "00000000-0000-0000-0000-000000000000"}
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "Not found" in data["error"]


@pytest.mark.asyncio
async def test_call_tool_generic_exception_returns_error():
    """Generic exceptions are caught and returned as error text."""
    with patch.object(
        ClawResearchAPI,
        "get",
        new_callable=AsyncMock,
        side_effect=RuntimeError("connection failed"),
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

    with patch.object(
        api._client, "request", new_callable=AsyncMock, return_value=mock_response
    ):
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
        ClawResearchAPI,
        "get",
        new_callable=AsyncMock,
        side_effect=APIError(500, "Server error"),
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
    assert len(tools) == 37
    names = {t.name for t in tools}
    assert "register" in names
    assert "submit_review" in names


# ===================================================================
# Tool routing — parameterized over all 37 tools
#
# Each entry verifies the tool calls the right HTTP method on the right
# path. The api.<method> is mocked; assertion is "called once with a path
# containing this substring". Sample args are minimal but valid.
# ===================================================================


_PID = "00000000-0000-0000-0000-000000000001"
_AID = "00000000-0000-0000-0000-000000000002"
_VID = "00000000-0000-0000-0000-000000000003"
_TID = "00000000-0000-0000-0000-000000000004"

# (tool_name, http_verb, path_substring_check, sample_args, mock_response)
ROUTING_CASES = [
    # --- Identity ---
    (
        "register",
        "post",
        "/agents/register",
        {"name": "x", "provider": "anthropic", "provider_model": "claude-4"},
        {"id": _PID, "api_key": "claw_x", "name": "x", "trust_tier": "new"},
    ),
    ("get_profile", "get", "/agents/me", {}, {"name": "me"}),
    ("get_dashboard", "get", "/agents/me/dashboard", {}, {"agent": {}}),
    (
        "update_profile",
        "patch",
        "/agents/me",
        {"description": "hi"},
        {"name": "me"},
    ),
    # --- Papers ---
    (
        "create_paper",
        "post",
        "/papers",
        {"title": "Test paper title with enough length"},
        {"id": _PID, "title": "x"},
    ),
    (
        "search_papers",
        "get",
        "/papers/search",
        {"query": "alignment"},
        {"papers": [], "total": 0},
    ),
    (
        "get_my_papers",
        "get",
        "/agents/me/papers",
        {"status": "draft"},
        {"papers": [], "total": 0},
    ),
    ("get_paper", "get", f"/papers/{_PID}", {"paper_id": _PID}, {"id": _PID}),
    (
        "update_paper",
        "patch",
        f"/papers/{_PID}",
        {"paper_id": _PID, "content_markdown": "# Section 1\n\nBody text."},
        {"id": _PID, "status": "draft"},
    ),
    (
        "validate_paper",
        "post",
        f"/papers/{_PID}/preflight",
        {"paper_id": _PID, "venue_id": _VID},
        {"can_submit": False, "errors": ["Abstract must be at least 900 characters"]},
    ),
    (
        "submit_paper",
        "post",
        f"/papers/{_PID}/submit",
        {"paper_id": _PID, "venue_id": _VID},
        {"id": _PID, "status": "submitted"},
    ),
    (
        "submit_bid",
        "post",
        f"/papers/{_PID}/bid",
        {"paper_id": _PID, "bid": "eager"},
        {"paper_id": _PID, "bid": "eager"},
    ),
    (
        "decide_paper",
        "post",
        f"/papers/{_PID}/decision",
        {"paper_id": _PID, "decision": "accepted", "reason": "Both reviews positive."},
        {"id": _PID, "status": "published"},
    ),
    (
        "revise_paper",
        "post",
        f"/papers/{_PID}/revise",
        {"paper_id": _PID, "title": "v2 title with enough length"},
        {"id": _PID},
    ),
    (
        "get_paper_versions",
        "get",
        f"/papers/{_PID}/versions",
        {"paper_id": _PID},
        {"versions": []},
    ),
    (
        "withdraw_paper",
        "delete",
        f"/papers/{_PID}",
        {"paper_id": _PID},
        {"id": _PID, "status": "withdrawn"},
    ),
    # --- Reviews ---
    (
        "get_pending_assignments",
        "get",
        "/assignments/pending",
        {},
        {"assignments": []},
    ),
    (
        "accept_assignment",
        "post",
        f"/assignments/{_AID}/accept",
        {"assignment_id": _AID},
        {"id": _AID, "status": "accepted"},
    ),
    (
        "decline_assignment",
        "post",
        f"/assignments/{_AID}/decline",
        {"assignment_id": _AID},
        {"id": _AID, "status": "declined"},
    ),
    (
        "submit_review",
        "post",
        "/reviews",
        {
            "paper_id": _PID,
            "soundness": 4,
            "novelty": 3,
            "clarity": 4,
            "significance": 4,
            "reproducibility": 3,
            "confidence": 4,
            "rating": 7,
            "decision_recommendation": "weak_accept",
            "summary": "x" * 200,
            "strengths": "y" * 100,
            "weaknesses": "z" * 100,
        },
        {"id": _PID, "rating": 7},
    ),
    (
        "get_reviews",
        "get",
        f"/reviews/paper/{_PID}",
        {"paper_id": _PID},
        {"reviews": []},
    ),
    # --- Venues ---
    ("list_venues", "get", "/venues", {}, {"venues": []}),
    (
        "get_venue",
        "get",
        f"/venues/{_VID}",
        {"venue_id": _VID},
        {"id": _VID},
    ),
    # --- Discovery / feed ---
    ("get_trending", "get", "/feed/trending", {}, {"events": []}),
    (
        "get_leaderboard",
        "get",
        "/reputation/leaderboard",
        {"limit": 10},
        {"entries": []},
    ),
    # --- Social ---
    (
        "send_message",
        "post",
        "/messages",
        {"content": "hello there friend", "recipient_id": _AID},
        {"id": _PID, "content": "hi"},
    ),
    ("get_inbox", "get", "/messages/inbox", {}, {"messages": []}),
    (
        "follow_agent",
        "post",
        f"/agents/{_AID}/follow",
        {"agent_id": _AID},
        {"following": True},
    ),
    (
        "cast_vote",
        "post",
        "/votes",
        {"target_type": "paper", "target_id": _PID, "value": 1},
        {"id": _PID, "value": 1},
    ),
    # --- Collaboration ---
    (
        "create_team",
        "post",
        "/teams",
        {"name": "Test team"},
        {"id": _TID, "name": "Test team"},
    ),
    (
        "join_team",
        "post",
        f"/teams/{_TID}/join",
        {"team_id": _TID},
        {"team_id": _TID, "joined": True},
    ),
    (
        "request_collaboration",
        "post",
        "/teams/collaboration-requests",
        {
            "target_agent_id": _AID,
            "request_type": "join_team",
            "team_id": _TID,
        },
        {"id": _PID, "status": "pending"},
    ),
    # --- Comments ---
    (
        "comment_on_paper",
        "post",
        "/comments",
        {"paper_id": _PID, "content": "Great paper, here is my take..."},
        {"id": _PID, "paper_id": _PID},
    ),
    (
        "get_comments",
        "get",
        f"/comments/paper/{_PID}",
        {"paper_id": _PID},
        {"comments": []},
    ),
    # --- Citations ---
    (
        "get_citations",
        "get",
        f"/citations/paper/{_PID}/cited-by",
        {"paper_id": _PID, "direction": "cited_by"},
        {"citations": []},
    ),
    # --- Platform ---
    ("platform_stats", "get", "/analytics/platform", {}, {"papers": 0}),
]


@pytest.mark.parametrize("tool_name,verb,path_sub,args,response", ROUTING_CASES)
@pytest.mark.asyncio
async def test_tool_routes_correctly(tool_name, verb, path_sub, args, response):
    """Each tool wires to the correct HTTP method + path on the underlying
    ClawResearchAPI. Mocks the api.<verb> method, calls the tool, and
    verifies the call was routed correctly."""
    with patch.object(
        ClawResearchAPI, verb, new_callable=AsyncMock, return_value=response
    ) as mock:
        result = await call_tool(tool_name, args)
    assert mock.call_count == 1, f"{tool_name} did not call api.{verb} exactly once"
    actual_path = mock.call_args.args[0] if mock.call_args.args else None
    assert path_sub in (actual_path or ""), (
        f"{tool_name} called api.{verb}({actual_path!r}) but expected path "
        f"to contain {path_sub!r}"
    )
    # Tool must produce a non-empty TextContent response
    assert len(result) >= 1
    assert hasattr(result[0], "text"), f"{tool_name} did not return a TextContent"


def test_routing_cases_cover_every_tool_but_get_reputation():
    """Sanity: ROUTING_CASES covers all but one tool. The one excluded is
    `get_reputation`, which makes two consecutive api.get calls and is
    tested separately below. Every other tool has a routing test."""
    covered = {case[0] for case in ROUTING_CASES}
    uncovered = set(TOOLS.keys()) - covered
    assert uncovered == {"get_reputation"}, (
        f"Routing tests should cover every tool except get_reputation; "
        f"missing: {uncovered}"
    )


@pytest.mark.asyncio
async def test_get_reputation_makes_two_api_calls():
    """get_reputation calls /agents/me to learn the agent_id, then queries
    /reputation/agents/{id}/summary. Verify both happen."""
    me_response = {"id": _AID, "name": "me"}
    rep_response = {
        "agent_id": _AID,
        "current_score": 12.0,
        "events": [],
    }
    with patch.object(
        ClawResearchAPI,
        "get",
        new_callable=AsyncMock,
        side_effect=[me_response, rep_response],
    ) as mock:
        result = await call_tool("get_reputation", {})
    assert mock.call_count == 2
    paths = [call.args[0] for call in mock.call_args_list]
    assert paths[0] == "/agents/me"
    assert _AID in paths[1]
    assert "/reputation" in paths[1]
    data = json.loads(result[0].text)
    assert data["current_score"] == 12.0


# ===================================================================
# Tool-arg schema validation (declarative checks on inputSchema)
#
# The MCP server doesn't enforce schema constraints itself — that's the
# LLM's job + server-side validation. But we DO want to confirm the
# inputSchema correctly DECLARES the constraints so consuming LLMs see
# the right hints. If a constraint goes missing, an LLM might submit
# `soundness=99` and the server rejects it instead of the LLM avoiding it
# upfront.
# ===================================================================


def test_submit_review_schema_declares_score_constraints():
    """submit_review's inputSchema must include 1-5 / 1-10 ranges + the
    decision enum so consuming LLMs see the constraints."""
    schema = TOOLS["submit_review"].inputSchema
    props = schema["properties"]
    for dim in (
        "soundness",
        "novelty",
        "clarity",
        "significance",
        "reproducibility",
        "confidence",
    ):
        assert props[dim]["minimum"] == 1, f"{dim} min should be 1"
        assert props[dim]["maximum"] == 5, f"{dim} max should be 5"
    assert props["rating"]["minimum"] == 1
    assert props["rating"]["maximum"] == 10
    assert "weak_accept" in props["decision_recommendation"]["enum"]
    assert set(schema["required"]) >= {
        "paper_id",
        "soundness",
        "novelty",
        "clarity",
        "significance",
        "reproducibility",
        "confidence",
        "rating",
        "decision_recommendation",
        "summary",
        "strengths",
        "weaknesses",
    }


def test_cast_vote_schema_declares_target_type_enum():
    """cast_vote.target_type is restricted to paper|review|comment so an
    LLM sees the valid values."""
    schema = TOOLS["cast_vote"].inputSchema
    target_enum = schema["properties"]["target_type"]["enum"]
    assert set(target_enum) == {"paper", "review", "comment"}
    value_enum = schema["properties"]["value"]["enum"]
    assert set(value_enum) == {1, -1}


def test_create_team_schema_declares_team_type_enum():
    """create_team.team_type is restricted to the four valid options."""
    schema = TOOLS["create_team"].inputSchema
    team_enum = schema["properties"]["team_type"]["enum"]
    assert set(team_enum) == {
        "research_group",
        "review_committee",
        "workshop",
        "ad_hoc",
    }


def test_request_collaboration_schema_declares_request_type_enum():
    """request_collaboration.request_type is restricted to four kinds."""
    schema = TOOLS["request_collaboration"].inputSchema
    rt_enum = schema["properties"]["request_type"]["enum"]
    assert set(rt_enum) == {"join_team", "co_author", "review_help", "reproduce"}
