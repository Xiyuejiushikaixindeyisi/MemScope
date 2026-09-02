"""Real-process startup and shutdown smoke test for the Mock Model API."""

import json
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_mock_model_uvicorn_process_serves_embedding_and_stops_cleanly() -> None:
    port = _unused_local_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "memscope.mock_model_api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "1",
        ],
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
                    f"http://127.0.0.1:{port}/health", timeout=0.2
                ) as response:
                    ready = response.status == 200
                    if ready:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.05)
        assert ready, process.communicate(timeout=1)
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/embeddings",
            data=b'{"model":"smoke","input":"fact"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=1) as response:  # noqa: S310 - fixed HTTP URL
            body = json.loads(response.read())
        assert response.status == 200
        assert len(body["data"][0]["embedding"]) == 16
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)

    stdout, stderr = process.communicate()
    assert process.returncode in {0, -signal.SIGTERM}, (stdout, stderr)
    assert "Application shutdown complete" in stderr
    assert "fact" not in stdout + stderr
