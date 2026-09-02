"""One no-key smoke path across Adapter, Raw Store and Fake Gateway."""

from pathlib import Path

import httpx

from memscope.app import create_app
from memscope.application import MemoryOperations
from memscope.memory_gateway import FakeMemoryGateway
from memscope.raw_store import SqliteRawStore
from tests.support import make_settings


async def test_fake_memory_path_add_is_immediately_searchable(tmp_path: Path) -> None:
    store = await SqliteRawStore.open(tmp_path / "smoke.db", busy_timeout_ms=1000)
    gateway = FakeMemoryGateway()
    application = create_app(
        make_settings(), operations=MemoryOperations(raw_store=store, gateway=gateway)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        added = await client.post(
            "/add",
            json={
                "request_id": "smoke-request",
                "user_id": "smoke-user",
                "session_id": "smoke-session",
                "messages": [{"role": "user", "content": "launch code orchid"}],
            },
        )
        searched = await client.post(
            "/search",
            json={"query": "launch code", "user_id": "smoke-user", "top_k": 3},
        )

    assert added.status_code == 200
    assert searched.status_code == 200
    assert [item["content"] for item in searched.json()["data"]] == ["launch code orchid"]
    await gateway.close()
    await store.close()
