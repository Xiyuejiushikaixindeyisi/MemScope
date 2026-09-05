#!/usr/bin/env python3
"""Run sanitized, bounded preflight checks for configured model APIs."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def _read_private_env(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("private env file is missing or is a symbolic link")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError("private env file must be mode 0600 or stricter")

    settings: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            raise ValueError(f"invalid private env entry at line {line_number}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        settings[key] = value
    return settings


def _required(settings: dict[str, str], name: str) -> str:
    value = settings.get(name, "").strip()
    if not value or "replace-with-" in value:
        raise ValueError(f"required setting is missing or still a placeholder: {name}")
    return value


def _boolean(settings: dict[str, str], name: str, default: bool) -> bool:
    raw = settings.get(name, "true" if default else "false").strip().lower()
    if raw not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return raw == "true"


def _endpoint(base: str, suffix: str) -> str:
    return f"{base.rstrip('/')}/{suffix.lstrip('/')}"


def _api_url(settings: dict[str, str], name: str) -> str:
    value = _required(settings, name)
    scheme = urlsplit(value).scheme
    if scheme not in {"http", "https"}:
        raise ValueError(f"{name} must use HTTP or HTTPS")
    if scheme == "http" and not _boolean(settings, "MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP", False):
        raise ValueError(f"{name} HTTP requires MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP=true")
    return value


def _request_json(
    url: str,
    api_key: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> tuple[dict[str, Any], dict[str, str]]:
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ValueError("model API URL must use HTTP or HTTPS")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(  # noqa: S310 - scheme is allowlisted above
        url, data=body, headers=headers, method="GET" if body is None else "POST"
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - scheme is allowlisted above
            request, timeout=timeout
        ) as response:
            response_body = response.read(2 * 1024 * 1024 + 1)
            if len(response_body) > 2 * 1024 * 1024:
                raise ValueError("model API response exceeded the preflight limit")
            parsed = json.loads(response_body)
            if not isinstance(parsed, dict):
                raise ValueError("model API response is not a JSON object")
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return parsed, response_headers
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"model API returned HTTP {error.code}") from None
    except urllib.error.URLError:
        raise ConnectionError("model API request failed") from None
    except json.JSONDecodeError:
        raise ValueError("model API returned invalid JSON") from None


def _model_ids(response: dict[str, Any]) -> set[str]:
    rows = response.get("data")
    if not isinstance(rows, list):
        raise ValueError("model list response has no data array")
    return {
        model_id
        for row in rows
        if isinstance(row, dict) and isinstance(model_id := row.get("id"), str)
    }


def _verify_model_visible(response: dict[str, Any], expected: str) -> None:
    if expected not in _model_ids(response):
        raise ValueError("configured model is not visible to the API key")


def run_preflight(
    settings: dict[str, str],
    *,
    allow_inference: bool,
    timeout: float,
    include_reranker: bool = False,
) -> list[str]:
    if timeout <= 0 or timeout > 120:
        raise ValueError("timeout must be greater than 0 and at most 120 seconds")

    llm_base = _api_url(settings, "MEMRADER_API_BASE")
    llm_key = _required(settings, "MEMRADER_API_KEY")
    llm_model = _required(settings, "MEMRADER_MODEL")
    embedding_base = _api_url(settings, "MOS_EMBEDDER_API_BASE")
    embedding_key = _required(settings, "MOS_EMBEDDER_API_KEY")
    embedding_model = _required(settings, "MOS_EMBEDDER_MODEL")
    embedding_dimension = int(_required(settings, "EMBEDDING_DIMENSION"))
    if embedding_dimension <= 0:
        raise ValueError("EMBEDDING_DIMENSION must be positive")

    passed: list[str] = []
    llm_models, _ = _request_json(_endpoint(llm_base, "models"), llm_key, timeout=timeout)
    _verify_model_visible(llm_models, llm_model)
    passed.append("glm_models")

    embedding_models, _ = _request_json(
        _endpoint(embedding_base, "models"), embedding_key, timeout=timeout
    )
    _verify_model_visible(embedding_models, embedding_model)
    passed.append("embedding_models")

    if not allow_inference:
        return passed

    llm_payload: dict[str, Any] = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": "Return one JSON object only."},
            {"role": "user", "content": 'Return exactly {"ok":true}.'},
        ],
        "max_tokens": 32,
        "temperature": 0,
    }
    thinking_type = settings.get("MEMRADER_THINKING_TYPE", "").strip().lower()
    if thinking_type:
        if thinking_type not in {"enabled", "disabled"}:
            raise ValueError("MEMRADER_THINKING_TYPE must be enabled or disabled")
        llm_payload["thinking"] = {"type": thinking_type}
    response_format = settings.get("MEMRADER_RESPONSE_FORMAT", "").strip().lower()
    if response_format:
        if response_format != "json_object":
            raise ValueError("MEMRADER_RESPONSE_FORMAT must be json_object")
        llm_payload["response_format"] = {"type": response_format}
    llm_response, _ = _request_json(
        _endpoint(llm_base, "chat/completions"),
        llm_key,
        payload=llm_payload,
        timeout=timeout,
    )
    choices = llm_response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("LLM response has no choice")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM response content is empty")
    if response_format and not isinstance(json.loads(content), dict):
        raise ValueError("LLM response content is not a JSON object")
    passed.append("llm")

    embedding_payload: dict[str, Any] = {
        "model": embedding_model,
        "input": ["MemScope API preflight"],
    }
    if _boolean(settings, "MOS_EMBEDDER_SEND_DIMENSIONS", True):
        embedding_payload["dimensions"] = embedding_dimension
    embedding_response, _ = _request_json(
        _endpoint(embedding_base, "embeddings"),
        embedding_key,
        payload=embedding_payload,
        timeout=timeout,
    )
    embedding_rows = embedding_response.get("data")
    if not isinstance(embedding_rows, list) or len(embedding_rows) != 1:
        raise ValueError("embedding response count mismatch")
    embedding = embedding_rows[0].get("embedding") if isinstance(embedding_rows[0], dict) else None
    if not isinstance(embedding, list) or len(embedding) != embedding_dimension:
        raise ValueError("embedding response dimension mismatch")
    passed.append("embedding")

    backends = {
        settings.get("MOS_RERANKER_BACKEND", "cosine_local").strip().lower(),
        settings.get("MOS_FEEDBACK_RERANKER_BACKEND", "cosine_local").strip().lower(),
    }
    if include_reranker or backends.intersection({"http_bge", "http_bge_strategy"}):
        reranker_url = _api_url(settings, "MOS_RERANKER_URL")
        reranker_key = _required(settings, "MOS_RERANKER_API_KEY")
        reranker_model = _required(settings, "MOS_RERANKER_MODEL")
        reranker_response, reranker_headers = _request_json(
            reranker_url,
            reranker_key,
            payload={
                "model": reranker_model,
                "query": "capital of France",
                "documents": ["Berlin", "Paris", "Madrid"],
                "top_n": 2,
                "return_documents": False,
            },
            timeout=timeout,
        )
        rows = reranker_response.get("results")
        if not isinstance(rows, list) or len(rows) != 2:
            raise ValueError("reranker response count mismatch")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("index"), int)
                or not isinstance(row.get("relevance_score"), int | float)
            ):
                raise ValueError("unexpected reranker response schema")
        _ = reranker_headers.get("x-siliconcloud-trace-id")
        passed.append("reranker")

    return passed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate model visibility and optionally run bounded inference smoke tests."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--env-file", type=Path)
    source.add_argument(
        "--from-environment",
        action="store_true",
        help="Read an already-exported environment without printing any values.",
    )
    parser.add_argument(
        "--allow-inference",
        action="store_true",
        help="Permit one 32-token LLM request and one single-input embedding request; "
        "also test reranking when an external backend is enabled.",
    )
    parser.add_argument(
        "--include-reranker",
        action="store_true",
        help="Also test the configured external reranker without enabling it in Compose.",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    if args.include_reranker and not args.allow_inference:
        parser.error("--include-reranker requires --allow-inference")

    try:
        settings = dict(os.environ) if args.from_environment else _read_private_env(args.env_file)
        passed = run_preflight(
            settings,
            allow_inference=args.allow_inference,
            timeout=args.timeout,
            include_reranker=args.include_reranker,
        )
    except (ConnectionError, RuntimeError, ValueError) as error:
        print(f"model API preflight failed: {error}", file=sys.stderr)
        return 1

    for check in passed:
        print(f"model API preflight passed: {check}")
    if not args.allow_inference:
        print("inference smoke skipped; rerun with --allow-inference after reviewing cost")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
