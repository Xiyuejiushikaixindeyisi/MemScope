"""HTTP contract tests for the isolated no-key Mock Model API."""

import asyncio
import json
import math

import httpx
import pytest

from memscope.mock_model_api.app import create_mock_model_app


def _transport(**kwargs: object) -> httpx.ASGITransport:
    return httpx.ASGITransport(app=create_mock_model_app(**kwargs))  # type: ignore[arg-type]


async def test_health_and_chat_envelope_are_deterministic_and_configurable() -> None:
    transport = _transport(chat_content='{"answer": 42}')
    payload = {
        "model": "mock-chat",
        "messages": [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "question"},
        ],
        "temperature": 0,
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        first = await client.post("/v1/chat/completions", json=payload)
        second = await client.post("/v1/chat/completions", json=payload)

    assert health.json() == {"status": "ok"}
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert json.loads(first.json()["choices"][0]["message"]["content"]) == {"answer": 42}
    assert first.json()["created"] == 0
    assert first.json()["usage"]["total_tokens"] == 0


async def test_chat_order_changes_stable_id_and_default_content() -> None:
    transport = _transport()
    first = {"model": "m", "messages": [{"role": "user", "content": "a"}]}
    second = {
        "model": "m",
        "messages": [{"role": "assistant", "content": "a"}],
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [
            await client.post("/v1/chat/completions", json=payload) for payload in (first, second)
        ]

    assert responses[0].json()["id"] != responses[1].json()["id"]
    assert responses[0].json()["choices"][0]["message"]["content"] == '{"memories":[]}'


async def test_embeddings_preserve_order_dimension_norm_unicode_and_empty_string() -> None:
    transport = _transport(embedding_dimension=7)
    payload = {"model": "mock-embedding", "input": ["same", "不同", "", "same"]}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/embeddings", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert [item["index"] for item in body["data"]] == [0, 1, 2, 3]
    vectors = [item["embedding"] for item in body["data"]]
    assert all(len(vector) == 7 for vector in vectors)
    assert all(
        math.sqrt(sum(value * value for value in vector)) == pytest.approx(1) for vector in vectors
    )
    assert vectors[0] == vectors[3]
    assert vectors[0] != vectors[1]


@pytest.mark.parametrize(
    ("endpoint", "failure", "status", "code"),
    [
        ("chat/completions", "rate_limit", 429, "mock.rate_limited"),
        ("chat/completions", "upstream_error", 500, "mock.upstream_error"),
        ("chat/completions", "unknown", 400, "mock.failure.invalid"),
        ("chat/completions", "dimension_mismatch", 400, "mock.failure.unsupported"),
        ("embeddings", "rate_limit", 429, "mock.rate_limited"),
    ],
)
async def test_safe_failure_statuses(endpoint: str, failure: str, status: int, code: str) -> None:
    payload: dict[str, object] = {"model": "m"}
    payload["messages" if endpoint.startswith("chat") else "input"] = (
        [{"role": "user", "content": "secret"}] if endpoint.startswith("chat") else "secret"
    )
    async with httpx.AsyncClient(transport=_transport(), base_url="http://test") as client:
        response = await client.post(
            f"/v1/{endpoint}",
            json=payload,
            headers={"X-MemScope-Mock-Failure": failure},
        )

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "secret" not in response.text


async def test_invalid_json_and_dimension_mismatch_faults_are_exact() -> None:
    async with httpx.AsyncClient(
        transport=_transport(embedding_dimension=3), base_url="http://test"
    ) as client:
        invalid = await client.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "x"}]},
            headers={"X-MemScope-Mock-Failure": "invalid_json"},
        )
        mismatch = await client.post(
            "/v1/embeddings",
            json={"model": "m", "input": "x"},
            headers={"X-MemScope-Mock-Failure": "dimension_mismatch"},
        )

    assert invalid.status_code == 200
    with pytest.raises(json.JSONDecodeError):
        invalid.json()
    assert len(mismatch.json()["data"][0]["embedding"]) == 4


async def test_timeout_fault_is_cancellable() -> None:
    async with httpx.AsyncClient(
        transport=_transport(timeout_delay_ms=200), base_url="http://test"
    ) as client:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                client.post(
                    "/v1/embeddings",
                    json={"model": "m", "input": "x"},
                    headers={"X-MemScope-Mock-Failure": "timeout"},
                ),
                timeout=0.02,
            )


async def test_timeout_fault_completes_when_client_allows_delay() -> None:
    async with httpx.AsyncClient(
        transport=_transport(timeout_delay_ms=10), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/embeddings",
            json={"model": "m", "input": "x"},
            headers={"X-MemScope-Mock-Failure": "timeout"},
        )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "m", "messages": [{"role": "user", "content": "secret"}], "stream": True},
        {"model": " ", "messages": [{"role": "user", "content": "secret"}]},
        {"model": "m", "messages": []},
        {"model": "m", "messages": [{"role": "user", "content": " "}]},
        {"model": "m", "messages": [{"role": "user", "content": "x"}], "stream": False},
        {"model": " ", "input": "secret"},
        {"model": "m", "input": []},
    ],
)
async def test_invalid_requests_are_sanitized(payload: dict[str, object]) -> None:
    endpoint = "chat/completions" if "messages" in payload else "embeddings"
    async with httpx.AsyncClient(transport=_transport(), base_url="http://test") as client:
        response = await client.post(f"/v1/{endpoint}", json=payload)

    if payload.get("stream") is False:
        assert response.status_code == 200
    else:
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "request.invalid"
        assert "secret" not in response.text


async def test_duplicate_failure_header_is_rejected() -> None:
    async with httpx.AsyncClient(transport=_transport(), base_url="http://test") as client:
        response = await client.post(
            "/v1/embeddings",
            json={"model": "m", "input": "x"},
            headers=[
                ("X-MemScope-Mock-Failure", "rate_limit"),
                ("X-MemScope-Mock-Failure", "upstream_error"),
            ],
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "mock.failure.invalid"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"chat_content": "not-json"}, ValueError),
        ({"chat_content": 1}, TypeError),
        ({"embedding_dimension": True}, ValueError),
        ({"embedding_dimension": 0}, ValueError),
        ({"embedding_dimension": 4097}, ValueError),
        ({"timeout_delay_ms": True}, ValueError),
        ({"timeout_delay_ms": 9}, ValueError),
        ({"timeout_delay_ms": 5001}, ValueError),
    ],
)
def test_mock_app_factory_rejects_invalid_configuration(
    kwargs: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        create_mock_model_app(**kwargs)  # type: ignore[arg-type]
