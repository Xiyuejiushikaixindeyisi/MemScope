"""Tests for framework HTTP errors that do not reach contest operations."""

import httpx
import pytest

from memscope.app import create_app
from tests.support import make_settings


@pytest.mark.asyncio
async def test_not_found_and_method_not_allowed_use_safe_envelopes() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        not_found = await client.get("/missing?secret=must-not-appear")
        method_not_allowed = await client.get("/add")

    assert not_found.status_code == 404
    assert not_found.json() == {
        "error": {
            "code": "http.not_found",
            "message": "Resource not found",
            "retryable": False,
        }
    }
    assert method_not_allowed.status_code == 405
    assert method_not_allowed.json()["error"]["code"] == "http.method_not_allowed"
    assert "must-not-appear" not in not_found.text
