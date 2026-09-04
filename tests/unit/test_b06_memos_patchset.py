"""B06 guards for strict Search failures and sanitized fixed-source logs."""

import importlib.util
import py_compile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
PATCHER = ROOT / "docker" / "memos" / "apply_patchset.py"
SOURCE = ROOT / ".vendor-src" / "MemOS"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("b06_memos_patcher", PATCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_b06_search_patchset_compiles_and_propagates_search_errors(tmp_path: Path) -> None:
    results = _module().transformed(SOURCE)
    for relative, (_pre, updated, _post) in results.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(updated)
        py_compile.compile(destination, doraise=True)

    single = results["src/memos/multi_mem_cube/single_cube.py"][1]
    assert 'raise ValueError("unsupported Search mode")' in single
    assert 'self.logger.error("Error in search_text:' not in single
    assert "return self._fast_search(search_req, user_context)" in single
    assert "return self._fine_search(search_req, user_context)" in single
    assert "return self._mix_search(search_req, user_context)" in single


def test_b06_search_patchset_removes_reachable_query_prompt_and_response_logs() -> None:
    results = _module().transformed(SOURCE)
    searcher = results["src/memos/memories/textual/tree_text_memory/retrieve/searcher.py"][1]
    parser = results["src/memos/memories/textual/tree_text_memory/retrieve/task_goal_parser.py"][1]
    retrieve_utils = results[
        "src/memos/memories/textual/tree_text_memory/retrieve/retrieve_utils.py"
    ][1]
    single_cube = results["src/memos/multi_mem_cube/single_cube.py"][1]

    assert "Start query='" not in searcher
    assert "Retrieve from plugin: {query}" not in searcher
    assert "'{query}'" not in searcher
    assert "Query words: {query_words}" not in searcher
    assert '"Query: {} COT: {}"' not in searcher
    assert "traceback.format_exc()" not in searcher
    assert "Exception during chat generation: {e}" not in searcher
    assert "query_chars=%s" in searcher

    assert "LLM input is {prompt}" not in parser
    assert "LLM Response is {response}" not in parser
    assert "fine-parse query {query}" not in parser
    assert "Raw response:" not in parser
    assert "Parsing Goal query_chars=%s" in parser

    assert "Raw:\\n{response_text}" not in retrieve_utils
    assert "Unexpected error: {e}" not in retrieve_utils
    assert "Failed to decode JSON response" in retrieve_utils

    assert "additional search with hint: {missing_info_hint}" not in single_cube
    assert 'logger.info("Triggering additional Search")' in single_cube


def test_b06_compose_explicitly_disables_deferred_search_paths() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    for setting in ("FAST_GRAPH", "BM25_CALL", "VEC_COT_CALL", "FULLTEXT_CALL"):
        assert f'{setting}: "false"' in compose
