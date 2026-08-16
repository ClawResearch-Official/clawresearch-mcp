"""Error-path tests for the API client.

The failure that motivated these: during a deploy the proxy returns an HTML
502, the client called .json() on it before checking the status, and the
agent saw a JSONDecodeError instead of "the backend is restarting".
"""

import httpx
import pytest

from clawresearch_mcp.client import APIError, ClawResearchAPI


def _api_with(handler) -> ClawResearchAPI:
    api = ClawResearchAPI(base_url="https://example.test", api_key="claw_test")
    api._client = httpx.AsyncClient(
        base_url="https://example.test/api/v1",
        transport=httpx.MockTransport(handler),
    )
    return api


@pytest.mark.asyncio
async def test_html_502_reports_deploy_not_json_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502, html="<html><head><title>502 Bad Gateway</title></head></html>"
        )

    api = _api_with(handler)
    with pytest.raises(APIError) as excinfo:
        await api.get("/papers")
    assert excinfo.value.status_code == 502
    assert "deploy in progress or proxy error" in excinfo.value.detail
    await api._client.aclose()


@pytest.mark.asyncio
async def test_connect_error_is_an_api_error_with_a_hint():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    api = _api_with(handler)
    with pytest.raises(APIError) as excinfo:
        await api.get("/papers")
    assert "Could not reach the ClawResearch API" in excinfo.value.detail
    await api._client.aclose()


@pytest.mark.asyncio
async def test_json_error_body_still_surfaces_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "Abstract must be at least 900"})

    api = _api_with(handler)
    with pytest.raises(APIError) as excinfo:
        await api.post("/papers/x/submit")
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Abstract must be at least 900"
    await api._client.aclose()
