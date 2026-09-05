from __future__ import annotations

import importlib.util
import io
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest


def _load_module() -> Any:
    path = (
        Path(__file__).parents[2]
        / "技术难题-Agent-Memory-评测集（开源）-1.0"
        / "scripts"
        / "local_proxy_eval.py"
    )
    spec = importlib.util.spec_from_file_location("memscope_local_proxy_eval", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load local proxy evaluator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


proxy = _load_module()


class _Response:
    status = 200

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, _: int) -> bytes:
        return b'{"status":"ok"}'


def test_sensitive_output_must_be_outside_source_and_is_private(tmp_path: Path) -> None:
    eval_root = tmp_path / "eval"
    eval_root.mkdir()
    with pytest.raises(ValueError, match="outside"):
        proxy.prepare_sensitive_output(eval_root / "reports", eval_root)

    output = proxy.prepare_sensitive_output(tmp_path / "private-output", eval_root)
    assert output.stat().st_mode & 0o777 == 0o700
    proxy.write_json(output / "summary.json", {"official": False})
    assert (output / "summary.json").stat().st_mode & 0o777 == 0o600


def test_client_uses_env_credential_shape_and_bounded_429_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    sleeps: list[float] = []

    def fake_open(request: Any, *, timeout: float) -> _Response:
        calls.append((request, timeout))
        if len(calls) == 1:
            headers = Message()
            headers["Retry-After"] = "0"
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "rate limited",
                headers,
                io.BytesIO(b'{"private":"provider body"}'),
            )
        return _Response()

    monkeypatch.setattr(proxy.urllib.request, "urlopen", fake_open)
    monkeypatch.setattr(proxy.time, "sleep", sleeps.append)
    client = proxy.HttpClient(
        "http://127.0.0.1:8080",
        10,
        auth_mode="bearer",
        credential="unit-fixture",
        max_rate_limit_retries=1,
        initial_backoff_seconds=0.5,
    )

    status, body, _ = client.request("GET", "/health")

    assert status == 200
    assert body == {"status": "ok"}
    assert client.rate_limit_retries == 1
    assert sleeps == [0.5]
    assert calls[0][0].get_header("Authorization") == "Bearer unit-fixture"


def test_http_failure_does_not_echo_provider_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request: Any, *, timeout: float) -> _Response:
        headers = Message()
        raise urllib.error.HTTPError(
            request.full_url,
            500,
            "failed",
            headers,
            io.BytesIO(b"sensitive-provider-response"),
        )

    monkeypatch.setattr(proxy.urllib.request, "urlopen", fake_open)
    client = proxy.HttpClient("http://127.0.0.1:8080", 10)
    with pytest.raises(RuntimeError) as captured:
        client.request("GET", "/health")
    assert "sensitive-provider-response" not in str(captured.value)


def test_client_rejects_credentials_embedded_in_url() -> None:
    with pytest.raises(ValueError, match="without credentials"):
        proxy.HttpClient("https://user:secret@example.invalid", 10)
