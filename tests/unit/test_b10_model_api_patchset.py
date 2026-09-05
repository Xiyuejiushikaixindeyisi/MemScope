"""B10 guards for development model APIs and opt-in external reranking."""

import ast
import importlib.util
import math
import os
import py_compile
import re
import subprocess
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATCHER = ROOT / "docker" / "memos" / "apply_patchset.py"
SOURCE = ROOT / ".vendor-src" / "MemOS"
PREFLIGHT = ROOT / "scripts" / "preflight_model_apis.py"
ENTRYPOINT = ROOT / "docker" / "memos" / "entrypoint.sh"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("b10_memos_patcher", PATCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _preflight_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("b10_model_api_preflight", PREFLIGHT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rendered(tmp_path: Path) -> dict[str, str]:
    results = _module().transformed(SOURCE)
    rendered = {path: updated for path, (_pre, updated, _post) in results.items()}
    for relative, updated in rendered.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(updated, encoding="utf-8")
        py_compile.compile(destination, doraise=True)
    return rendered


def _load_isolated_class(source: str, class_name: str, namespace: dict) -> type:
    tree = ast.parse(source)
    selected = []
    for node in tree.body:
        keep = False
        if isinstance(node, ast.ImportFrom):
            keep = node.module == "__future__"
        elif isinstance(node, ast.Assign):
            keep = any(
                isinstance(target, ast.Name) and target.id in {"_TAG1", "DEFAULT_BOOST_WEIGHTS"}
                for target in node.targets
            )
        elif isinstance(node, ast.FunctionDef):
            keep = node.name in {"_sanitize_unicode", "_value_matches"}
        elif isinstance(node, ast.ClassDef):
            keep = node.name == class_name
        if keep:
            selected.append(node)
    isolated = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(isolated, "<isolated-vendor-class>", "exec"), namespace)  # noqa: S102
    return namespace[class_name]


def test_glm_provider_options_are_explicit_and_optional(tmp_path: Path) -> None:
    rendered = _rendered(tmp_path)
    config = rendered["src/memos/api/config.py"]

    assert 'os.getenv("MEMRADER_THINKING_TYPE", "")' in config
    assert 'os.getenv("MEMRADER_RESPONSE_FORMAT", "")' in config
    assert 'extra_body["thinking"] = {"type": thinking_type}' in config
    assert 'extra_body["response_format"] = {"type": response_format}' in config
    assert "MEMRADER_THINKING_TYPE must be enabled or disabled" in config
    assert "MEMRADER_RESPONSE_FORMAT must be json_object" in config


def test_embedding_dimension_contract_is_separate_from_request_shape(tmp_path: Path) -> None:
    rendered = _rendered(tmp_path)
    config = rendered["src/memos/api/config.py"]
    embedder_config = rendered["src/memos/configs/embedder.py"]
    embedder = rendered["src/memos/embedders/universal_api.py"]

    assert '"MOS_EMBEDDER_SEND_DIMENSIONS", "true"' in config
    assert "send_dimensions: bool = Field(" in embedder_config
    assert "if self.config.send_dimensions else None" in embedder
    assert "embedding response count mismatch" in embedder
    assert "embedding response dimension mismatch" in embedder
    assert "Embeddings request ended with error: {e}" not in embedder


def test_embedding_runtime_omits_dimensions_and_checks_response(tmp_path: Path) -> None:
    embedder_source = _rendered(tmp_path)["src/memos/embedders/universal_api.py"]

    class BaseEmbedder:
        pass

    class BadRequestError(Exception):
        pass

    embedder_class = _load_isolated_class(
        embedder_source,
        "UniversalAPIEmbedder",
        {
            "BaseEmbedder": BaseEmbedder,
            "BadRequestError": BadRequestError,
            "UniversalAPIEmbedderConfig": object,
            "log_embedding_call": lambda function: function,
            "logger": SimpleNamespace(warning=lambda *args, **kwargs: None),
            "os": os,
        },
    )
    instance = object.__new__(embedder_class)
    instance.config = SimpleNamespace(embedding_dims=3, send_dimensions=False)
    observed: list[dict] = []

    class Embeddings:
        @staticmethod
        def create(**kwargs: object) -> SimpleNamespace:
            observed.append(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])

    client = SimpleNamespace(embeddings=Embeddings())
    assert instance._call_embeddings_api(client, "BAAI/bge-m3", ["text"], 5) == [[0.1, 0.2, 0.3]]
    assert "dimensions" not in observed[0]

    instance.config = SimpleNamespace(embedding_dims=2, send_dimensions=False)
    with pytest.raises(ValueError, match="embedding response dimension mismatch"):
        instance._call_embeddings_api(client, "BAAI/bge-m3", ["text"], 5)


def test_http_reranker_is_authenticated_bounded_and_fail_closed(tmp_path: Path) -> None:
    rendered = _rendered(tmp_path)
    api_config = rendered["src/memos/api/config.py"]
    factory = rendered["src/memos/reranker/factory.py"]
    reranker = rendered["src/memos/reranker/http_bge.py"]

    assert '"token": os.getenv("MOS_RERANKER_API_KEY", "")' in api_config
    assert 'token=c.get("token", "")' in factory
    strategy_call = factory.split("return HTTPBGERerankerStrategy(", 1)[1]
    assert 'token=c.get("token", "")' not in strategy_call
    assert 'headers["Authorization"] = f"Bearer {self.token}"' in reranker
    assert '"top_n": min(top_k, len(documents))' in reranker
    assert '"return_documents": False' in reranker
    assert "HTTPBGERerankerSample" not in reranker
    assert "query_chars=%s document_count=%s" in reranker
    assert "fallback=lambda" not in reranker
    assert "unexpected reranker response schema" in reranker
    assert "Reranker retryable HTTP status=%s" in reranker
    assert "min(max(0, int(max_retries)), 2)" in reranker
    assert "min(max(0.0, float(retry_backoff_seconds)), 1.0)" in reranker
    assert "math.isfinite(score)" in reranker
    assert "reranker relevance score is invalid" in reranker
    assert "score_list += [0.0]" not in reranker


def test_http_reranker_runtime_sends_bearer_and_propagates_errors(tmp_path: Path) -> None:
    reranker_source = _rendered(tmp_path)["src/memos/reranker/http_bge.py"]
    observed: list[dict] = []

    class FakeRequestError(Exception):
        pass

    class FakeTimeoutError(FakeRequestError):
        pass

    class Response:
        def __init__(self, status_code: int, body: dict) -> None:
            self.status_code = status_code
            self.body = body
            self.headers = {"x-siliconcloud-trace-id": "trace-id"}

        def json(self) -> dict:
            return self.body

    responses = [
        Response(
            200,
            {
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.2},
                ]
            },
        )
    ]

    def post(*args: object, **kwargs: object) -> Response:
        observed.append(kwargs)
        return responses.pop(0)

    requests = SimpleNamespace(
        post=post,
        RequestException=FakeRequestError,
        Timeout=FakeTimeoutError,
    )

    class BaseReranker:
        pass

    reranker_class = _load_isolated_class(
        reranker_source,
        "HTTPBGEReranker",
        {
            "Any": object,
            "BaseReranker": BaseReranker,
            "Iterable": __import__("collections.abc").abc.Iterable,
            "concat_original_source": lambda items, source: items,
            "logger": SimpleNamespace(
                info=lambda *args, **kwargs: None,
                warning=lambda *args, **kwargs: None,
            ),
            "math": math,
            "re": re,
            "requests": requests,
            "time": time,
            "timed_with_status": lambda **kwargs: lambda function: function,
        },
    )
    reranker = reranker_class(
        "https://api.siliconflow.cn/v1/rerank",
        token="secret",
        model="BAAI/bge-reranker-v2-m3",
        max_retries=0,
    )
    items = [{"memory": "Berlin"}, {"memory": "Paris"}]
    ranked = reranker.rerank("capital of France", items, 2)

    assert [item for item, _score in ranked] == [items[1], items[0]]
    assert observed[0]["headers"]["Authorization"] == "Bearer secret"
    assert observed[0]["json"]["top_n"] == 2
    assert observed[0]["json"]["return_documents"] is False

    responses.append(Response(401, {}))
    with pytest.raises(RuntimeError, match="HTTP 401"):
        reranker.rerank("capital of France", items, 2)


def test_compose_keeps_external_reranker_off_by_default_but_wires_it() -> None:
    for compose_name in ("compose.yaml", "compose.release.yaml"):
        compose = (ROOT / compose_name).read_text(encoding="utf-8")
        assert 'MOS_RERANKER_BACKEND: "${MOS_RERANKER_BACKEND:-cosine_local}"' in compose
        assert (
            "MOS_FEEDBACK_RERANKER_BACKEND: "
            '"${MOS_FEEDBACK_RERANKER_BACKEND:-cosine_local}"' in compose
        )
        assert 'MOS_RERANKER_API_KEY: "${MOS_RERANKER_API_KEY:-}"' in compose
        assert 'MOS_RERANKER_URL: "${MOS_RERANKER_URL:-}"' in compose
        assert 'MEMRADER_THINKING_TYPE: "${MEMRADER_THINKING_TYPE:-}"' in compose
        assert 'MEMRADER_RESPONSE_FORMAT: "${MEMRADER_RESPONSE_FORMAT:-}"' in compose
        assert 'MOS_EMBEDDER_SEND_DIMENSIONS: "${MOS_EMBEDDER_SEND_DIMENSIONS:-true}"' in compose


def test_development_api_template_selects_approved_gate2_models() -> None:
    template = (ROOT / "deploy" / "development-api.env.example").read_text(encoding="utf-8")

    assert "MEMRADER_MODEL=glm-5.1" in template
    assert "MEMRADER_API_BASE=https://open.bigmodel.cn/api/paas/v4" in template
    assert "MEMRADER_THINKING_TYPE=disabled" in template
    assert "MEMRADER_RESPONSE_FORMAT=json_object" in template
    assert "MOS_EMBEDDER_MODEL=BAAI/bge-m3" in template
    assert "MOS_EMBEDDER_API_BASE=https://api.siliconflow.cn/v1" in template
    assert "MOS_EMBEDDER_SEND_DIMENSIONS=false" in template
    assert "EMBEDDING_DIMENSION=1024" in template
    assert "MOS_RERANKER_BACKEND=cosine_local" in template
    assert "MOS_FEEDBACK_RERANKER_BACKEND=cosine_local" in template
    assert "replace-with-private-key" in template


def test_preflight_uses_bounded_sanitized_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _preflight_module()
    observed: list[tuple[str, dict | None]] = []

    def fake_request(
        url: str,
        api_key: str,
        *,
        payload: dict | None = None,
        timeout: float,
    ) -> tuple[dict, dict[str, str]]:
        assert api_key in {"glm-secret", "silicon-secret"}
        assert timeout == 10
        observed.append((url, payload))
        if url.endswith("/models"):
            models = (
                ["glm-5.1"]
                if "bigmodel" in url
                else [
                    "BAAI/bge-m3",
                    "BAAI/bge-reranker-v2-m3",
                ]
            )
            return {"data": [{"id": model} for model in models]}, {}
        if url.endswith("/embeddings"):
            return {"data": [{"index": 0, "embedding": [0.0] * 1024}]}, {}
        if url.endswith("/chat/completions"):
            return {"choices": [{"message": {"content": '{"ok":true}'}}]}, {}
        if url.endswith("/rerank"):
            return {
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.2},
                ]
            }, {"x-siliconcloud-trace-id": "trace-id"}
        raise AssertionError(url)

    monkeypatch.setattr(module, "_request_json", fake_request)
    settings = {
        "MEMRADER_API_BASE": "https://open.bigmodel.cn/api/paas/v4",
        "MEMRADER_API_KEY": "glm-secret",
        "MEMRADER_MODEL": "glm-5.1",
        "MEMRADER_THINKING_TYPE": "disabled",
        "MEMRADER_RESPONSE_FORMAT": "json_object",
        "MOS_EMBEDDER_API_BASE": "https://api.siliconflow.cn/v1",
        "MOS_EMBEDDER_API_KEY": "silicon-secret",
        "MOS_EMBEDDER_MODEL": "BAAI/bge-m3",
        "MOS_EMBEDDER_SEND_DIMENSIONS": "false",
        "EMBEDDING_DIMENSION": "1024",
        "MOS_RERANKER_BACKEND": "cosine_local",
        "MOS_RERANKER_URL": "https://api.siliconflow.cn/v1/rerank",
        "MOS_RERANKER_API_KEY": "silicon-secret",
        "MOS_RERANKER_MODEL": "BAAI/bge-reranker-v2-m3",
    }

    results = module.run_preflight(
        settings,
        allow_inference=True,
        timeout=10,
        include_reranker=True,
    )

    assert results == ["glm_models", "embedding_models", "llm", "embedding", "reranker"]
    payloads = {url.rsplit("/", 1)[-1]: body for url, body in observed if body is not None}
    assert payloads["completions"]["max_tokens"] == 32
    assert payloads["completions"]["thinking"] == {"type": "disabled"}
    assert payloads["completions"]["response_format"] == {"type": "json_object"}
    assert "dimensions" not in payloads["embeddings"]
    assert payloads["rerank"]["top_n"] == 2
    assert payloads["rerank"]["return_documents"] is False


def test_preflight_models_only_makes_no_inference_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _preflight_module()
    observed: list[str] = []

    def fake_request(
        url: str,
        api_key: str,
        *,
        payload: dict | None = None,
        timeout: float,
    ) -> tuple[dict, dict[str, str]]:
        assert payload is None
        observed.append(url)
        model = "glm-5.1" if "bigmodel" in url else "BAAI/bge-m3"
        return {"data": [{"id": model}]}, {}

    monkeypatch.setattr(module, "_request_json", fake_request)
    settings = {
        "MEMRADER_API_BASE": "https://open.bigmodel.cn/api/paas/v4",
        "MEMRADER_API_KEY": "glm-secret",
        "MEMRADER_MODEL": "glm-5.1",
        "MOS_EMBEDDER_API_BASE": "https://api.siliconflow.cn/v1",
        "MOS_EMBEDDER_API_KEY": "silicon-secret",
        "MOS_EMBEDDER_MODEL": "BAAI/bge-m3",
        "EMBEDDING_DIMENSION": "1024",
    }

    assert module.run_preflight(settings, allow_inference=False, timeout=10) == [
        "glm_models",
        "embedding_models",
    ]
    assert all(url.endswith("/models") for url in observed)


def test_preflight_rejects_unapproved_plain_http() -> None:
    module = _preflight_module()
    settings = {
        "MEMRADER_API_BASE": "http://models.invalid/v1",
        "MEMRADER_API_KEY": "glm-secret",
        "MEMRADER_MODEL": "glm-5.1",
        "MOS_EMBEDDER_API_BASE": "https://api.siliconflow.cn/v1",
        "MOS_EMBEDDER_API_KEY": "silicon-secret",
        "MOS_EMBEDDER_MODEL": "BAAI/bge-m3",
        "EMBEDDING_DIMENSION": "1024",
        "MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP": "false",
    }

    with pytest.raises(ValueError, match="requires MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP=true"):
        module.run_preflight(settings, allow_inference=False, timeout=10)


def _run_entrypoint(tmp_path: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    environment = {
        "PATH": os.environ["PATH"],
        "MEMOS_BASE_PATH": str(tmp_path / "memos"),
        "FILE_LOCAL_PATH": str(tmp_path / "memos" / "files"),
        "MEMSCOPE_MODEL_PROFILE": "gateway",
        "MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP": "false",
        "MEMRADER_MODEL": "glm-5.1",
        "MEMRADER_API_BASE": "https://models.invalid/v1",
        "MEMRADER_API_KEY": "reader-secret",
        "MOS_EMBEDDER_MODEL": "BAAI/bge-m3",
        "MOS_EMBEDDER_API_BASE": "https://models.invalid/v1",
        "MOS_EMBEDDER_API_KEY": "embedding-secret",
        "MOS_EMBEDDER_SEND_DIMENSIONS": "false",
        "EMBEDDING_DIMENSION": "1024",
        "MOS_RERANKER_BACKEND": "cosine_local",
        "MOS_FEEDBACK_RERANKER_BACKEND": "cosine_local",
        **overrides,
    }
    return subprocess.run(
        [str(ENTRYPOINT), "/bin/true"],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_entrypoint_keeps_reranker_local_without_external_secret(tmp_path: Path) -> None:
    assert _run_entrypoint(tmp_path).returncode == 0


def test_entrypoint_requires_external_reranker_credentials(tmp_path: Path) -> None:
    result = _run_entrypoint(tmp_path, MOS_RERANKER_BACKEND="http_bge")

    assert result.returncode != 0
    assert "MOS_RERANKER_URL" in result.stderr


def test_entrypoint_accepts_explicit_external_reranker(tmp_path: Path) -> None:
    result = _run_entrypoint(
        tmp_path,
        MOS_RERANKER_BACKEND="http_bge",
        MOS_RERANKER_URL="https://api.siliconflow.cn/v1/rerank",
        MOS_RERANKER_API_KEY="reranker-secret",
        MOS_RERANKER_MODEL="BAAI/bge-reranker-v2-m3",
    )

    assert result.returncode == 0, result.stderr


def test_entrypoint_rejects_unknown_glm_request_mode(tmp_path: Path) -> None:
    result = _run_entrypoint(tmp_path, MEMRADER_THINKING_TYPE="automatic")

    assert result.returncode == 64


def test_entrypoint_rejects_unhardened_reranker_strategy(tmp_path: Path) -> None:
    result = _run_entrypoint(
        tmp_path,
        MOS_RERANKER_BACKEND="http_bge_strategy",
        MOS_RERANKER_URL="https://api.siliconflow.cn/v1/rerank",
        MOS_RERANKER_API_KEY="reranker-secret",
        MOS_RERANKER_MODEL="BAAI/bge-reranker-v2-m3",
    )

    assert result.returncode == 64
