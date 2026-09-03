"""Guard tests for the exact B05 MemOS build-time compatibility patchset."""

import importlib.util
import json
import py_compile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATCHER = ROOT / "docker" / "memos" / "apply_patchset.py"
LOCK = ROOT / "docker" / "memos" / "PATCHSET_LOCK.json"
SOURCE = ROOT / ".vendor-src" / "MemOS"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("b05_memos_patcher", PATCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_patchset_preimages_postimages_and_compilation(tmp_path: Path) -> None:
    module = _module()
    lock = json.loads(LOCK.read_text())
    results = module.transformed(SOURCE)

    assert lock["schema"] == "memscope.memos.patchset.v1"
    assert set(results) == set(lock["files"])
    for relative, (preimage, updated, postimage) in results.items():
        assert lock["files"][relative] == {
            "pre_sha256": preimage,
            "post_sha256": postimage,
        }
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(updated)
        py_compile.compile(destination, doraise=True)


def test_patchset_contains_gate0_safety_guards() -> None:
    module = _module()
    results = module.transformed(SOURCE)
    rendered = {path: updated for path, (_pre, updated, _post) in results.items()}

    reader = rendered["src/memos/mem_reader/simple_struct.py"]
    assert "LLM returned an empty response" in reader
    assert "return self._safe_parse(response_text)" in reader
    assert "_deduplicate_exact" in reader
    assert '"message_id": item.get("message_id")' in reader
    assert "ordered[futures[future]] = future.result()" in reader
    assert "info.copy()" in reader
    assert "timeout=timeout_seconds" in reader
    assert "salvaged item" not in reader

    single = rendered["src/memos/multi_mem_cube/single_cube.py"]
    assert '"memscope_result_index": result_index' in single
    assert '"memscope_result_count": result_count' in single
    assert "MemScope Add deadline exceeded before write" in single
    assert "scheduler disabled" in single
    assert "Full request" not in single

    manager = rendered["src/memos/memories/textual/tree_text_memory/organize/manager.py"]
    assert 'logger.exception(\n                            "Batch add failed' in manager
    assert "                        raise\n" in manager

    openai = rendered["src/memos/llms/openai.py"]
    assert '"timeout": kwargs.get("timeout", self.config.timeout_seconds)' in openai
    assert "OpenAI LLM Request body" not in openai
    assert "Response from Azure OpenAI" in openai  # Azure is outside the B05 Add profile.


def test_patchset_rejects_source_drift(tmp_path: Path) -> None:
    module = _module()
    relative = next(iter(module.PATCHES))
    for path in module.PATCHES:
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((SOURCE / path).read_text())
    drifted = tmp_path / relative
    drifted.write_text(drifted.read_text() + "\n# deliberate source drift\n")

    with pytest.raises(RuntimeError):
        module.apply_patchset(tmp_path, verify_only=True)
