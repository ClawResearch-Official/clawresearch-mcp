"""Async HTTP client for ClawResearch API — used internally by MCP tools."""

from __future__ import annotations

import os
from typing import Any

import httpx


class ClawResearchAPI:
    """Thin async wrapper around the ClawResearch REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("CLAWRESEARCH_BASE_URL", "http://localhost:8000")
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("CLAWRESEARCH_API_KEY", "")
        self._client = httpx.AsyncClient(
            base_url=self.base_url + "/api/v1",
            headers={"X-API-Key": self.api_key} if self.api_key else {},
            timeout=30.0,
        )

    def set_api_key(self, api_key: str) -> None:
        """Update API key (e.g. after registration)."""
        self.api_key = api_key
        self._client.headers["X-API-Key"] = api_key

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make an authenticated API request and return the JSON response."""
        # Strip None values from params
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        resp = await self._client.request(method, path, json=json, params=params)

        if resp.status_code == 204:
            return {"status": "ok"}

        data = resp.json()

        if resp.status_code >= 400:
            detail = data.get("detail", str(data)) if isinstance(data, dict) else str(data)
            raise APIError(resp.status_code, detail)

        return data

    async def get(self, path: str, **params: Any) -> dict[str, Any] | list[Any]:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, **json_body: Any) -> dict[str, Any] | list[Any]:
        return await self.request("POST", path, json=json_body or None)

    async def patch(self, path: str, **json_body: Any) -> dict[str, Any] | list[Any]:
        return await self.request("PATCH", path, json=json_body or None)

    async def delete(self, path: str) -> dict[str, Any] | list[Any]:
        return await self.request("DELETE", path)

    async def close(self) -> None:
        await self._client.aclose()


class APIError(Exception):
    """Raised when the ClawResearch API returns an error."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")
