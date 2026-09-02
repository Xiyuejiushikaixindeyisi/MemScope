"""No-key ASGI and process startup smoke tests."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import httpx
import pytest

from memscope.app import create_app
from tests.support import make_settings


@pytest.mark.asyncio
async def test_asgi_app_registers_contest_routes_without_false_success() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        openapi = await client.get("/openapi.json")
        contest_responses = [
            await client.get("/health"),
            await client.post(
                "/add",
                json={
                    "request_id": "smoke:r",
                    "user_id": "smoke:u",
                    "session_id": "smoke:s",
                    "messages": [{"role": "user", "content": "fact"}],
                },
            ),
            await client.post(
                "/search",
                json={"query": "fact?", "user_id": "smoke:u", "top_k": 100},
            ),
        ]

    assert openapi.status_code == 200
    assert {"/health", "/add", "/search"} <= set(openapi.json()["paths"])
    assert all(response.status_code == 503 for response in contest_responses)


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_uvicorn_starts_and_stops_without_external_services() -> None:
    port = _unused_local_port()
    environment = os.environ.copy()
    environment.update({"APP_PROFILE": "core", "LOG_FORMAT": "json"})
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "memscope.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "1",
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 5
    ready = False
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/openapi.json", timeout=0.2
                ) as response:
                    ready = response.status == 200
                    if ready:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.05)
        assert ready, process.communicate(timeout=1)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=1) as response:
            paths = json.loads(response.read())["paths"]
        assert {"/health", "/add", "/search"} <= set(paths)
        with pytest.raises(urllib.error.HTTPError) as unavailable:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
        assert unavailable.value.code == 503
        assert json.loads(unavailable.value.read())["error"]["code"] == "service.unavailable"
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)

    stdout, stderr = process.communicate()
    assert process.returncode in {0, -signal.SIGTERM}, (stdout, stderr)
    assert "Application shutdown complete" in stderr


def test_invalid_environment_fails_before_application_ready() -> None:
    environment = os.environ.copy()
    environment["PORT"] = "not-a-port-secret-value"

    result = subprocess.run(
        [sys.executable, "-c", "import memscope.main"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "configuration.invalid" in combined_output
    assert "not-a-port-secret-value" not in combined_output
