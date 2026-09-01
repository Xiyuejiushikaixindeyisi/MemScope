#!/usr/bin/env python3
"""Validate the reconstructed pack and write a machine-readable report."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from collections import Counter
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_BENCHMARKS = {"LoCoMo-Refined": 500, "MemOps": 500}
EXPECTED_LOCOMO_AXES = {"single_hop": 167, "temporal": 167, "multi_hop": 166}
EXPECTED_MEMOPS_OPS = {"Remember": 132, "Update": 98, "Forget": 115, "Reflect": 155}
EXPECTED_MEMOPS_AXES = {
    "OperationTrace": 101,
    "TargetBinding": 101,
    "CandidateDisambiguation": 100,
    "OperationApplication": 100,
    "StateTransition": 98,
}


def load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number} is not a JSON object")
        rows.append(value)
    return rows


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate(eval_root: pathlib.Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    official = eval_root / "official"
    sample_paths = sorted((official / "samples").glob("*.json"))
    flat = load_jsonl(official / "questions.jsonl")
    manifest = load_json(official / "manifest.json")

    check(len(sample_paths) == 110, f"expected 110 sample files, got {len(sample_paths)}", errors)
    check(len(flat) == 1000, f"expected 1000 flat questions, got {len(flat)}", errors)

    flat_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in flat:
        key = (str(row.get("sample_id")), str(row.get("qid")))
        check(key not in flat_by_key, f"duplicate flat composite key: {key}", errors)
        flat_by_key[key] = row

    seen_users: set[str] = set()
    sample_item_count = 0
    benchmark_counts: Counter[str] = Counter()
    locomo_axes: Counter[str] = Counter()
    memops_ops: Counter[str] = Counter()
    memops_axes: Counter[str] = Counter()
    locomo_timestamps = 0
    sample_keys: set[tuple[str, str]] = set()

    for path in sample_paths:
        sample = load_json(path)
        for required in ("sample_id", "isolation", "add_phase", "search_items"):
            check(required in sample, f"{path.name}: missing {required}", errors)
        sample_id = str(sample.get("sample_id"))
        check(path.stem == sample_id, f"{path.name}: filename/sample_id mismatch", errors)
        isolation = sample.get("isolation") or {}
        user_id = isolation.get("user_id")
        check(isinstance(user_id, str) and bool(user_id), f"{path.name}: invalid user_id", errors)
        check(user_id not in seen_users, f"duplicate user_id: {user_id}", errors)
        if isinstance(user_id, str):
            seen_users.add(user_id)

        sessions = (sample.get("add_phase") or {}).get("sessions") or []
        actual_session_ids: list[str] = []
        for session in sessions:
            session_id = session.get("session_id")
            check(isinstance(session_id, str) and bool(session_id), f"{path.name}: bad session_id", errors)
            if isinstance(session_id, str):
                actual_session_ids.append(session_id)
            messages = session.get("messages") or []
            check(bool(messages), f"{path.name}/{session_id}: empty messages", errors)
            for index, message in enumerate(messages):
                check(
                    isinstance(message.get("role"), str) and bool(message.get("role")),
                    f"{path.name}/{session_id}/{index}: invalid role",
                    errors,
                )
                check(
                    isinstance(message.get("content"), str) and bool(message.get("content").strip()),
                    f"{path.name}/{session_id}/{index}: invalid content",
                    errors,
                )
                if "timestamp" in message:
                    check(
                        isinstance(message["timestamp"], int) and not isinstance(message["timestamp"], bool),
                        f"{path.name}/{session_id}/{index}: timestamp is not integer",
                        errors,
                    )
                    if sample_id.startswith("locomo_"):
                        locomo_timestamps += 1
        check(
            actual_session_ids == isolation.get("session_ids"),
            f"{path.name}: isolation.session_ids mismatch",
            errors,
        )

        benchmark = str((sample.get("source") or {}).get("benchmark") or "")
        operation_type = (sample.get("source") or {}).get("operation_type")
        for item in sample.get("search_items") or []:
            sample_item_count += 1
            key = (sample_id, str(item.get("qid")))
            check(key not in sample_keys, f"duplicate sample item key: {key}", errors)
            sample_keys.add(key)
            for required in ("qid", "question", "gold_answer"):
                check(required in item, f"{path.name}/{key[1]}: missing {required}", errors)
            check(key in flat_by_key, f"{path.name}/{key[1]}: missing flat row", errors)
            if key in flat_by_key:
                flat_row = flat_by_key[key]
                for field in ("question", "gold_answer", "eval_axis"):
                    check(
                        flat_row.get(field) == item.get(field),
                        f"{path.name}/{key[1]}: flat {field} mismatch",
                        errors,
                    )
            benchmark_counts[benchmark] += 1
            axis = str(item.get("eval_axis") or "")
            if benchmark == "LoCoMo-Refined":
                locomo_axes[axis] += 1
            elif benchmark == "MemOps":
                memops_ops[str(operation_type)] += 1
                memops_axes[axis] += 1

    check(sample_item_count == 1000, f"samples contain {sample_item_count} questions", errors)
    check(sample_keys == set(flat_by_key), "sample/flat composite key sets differ", errors)
    check(dict(benchmark_counts) == EXPECTED_BENCHMARKS, f"benchmark counts: {dict(benchmark_counts)}", errors)
    check(dict(locomo_axes) == EXPECTED_LOCOMO_AXES, f"LoCoMo axes: {dict(locomo_axes)}", errors)
    check(dict(memops_ops) == EXPECTED_MEMOPS_OPS, f"MemOps operations: {dict(memops_ops)}", errors)
    check(dict(memops_axes) == EXPECTED_MEMOPS_AXES, f"MemOps axes: {dict(memops_axes)}", errors)
    check(locomo_timestamps == 0, f"guide-compatible LoCoMo contains {locomo_timestamps} timestamps", errors)

    check(manifest.get("search_items") == 1000, "manifest search_items mismatch", errors)
    check(manifest.get("samples") == 110, "manifest sample count mismatch", errors)
    check(manifest.get("counts_by_benchmark") == EXPECTED_BENCHMARKS, "manifest benchmark counts mismatch", errors)

    unwanted = [
        eval_root / "mainfest.json",
        official / "mainfest.json",
        official / "question.jsonl",
        eval_root / ".cac",
    ]
    for path in unwanted:
        check(not path.exists(), f"obsolete path still present: {path.relative_to(eval_root)}", errors)

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "samples": len(sample_paths),
            "questions": len(flat),
            "benchmark": dict(sorted(benchmark_counts.items())),
            "locomo_axis": dict(sorted(locomo_axes.items())),
            "memops_operation_type": dict(sorted(memops_ops.items())),
            "memops_eval_axis": dict(sorted(memops_axes.items())),
            "guide_compatible_locomo_timestamps": locomo_timestamps,
        },
    }


def write_hashes(eval_root: pathlib.Path) -> pathlib.Path:
    output = eval_root / "reports" / "SHA256SUMS.txt"
    paths = sorted(
        path
        for path in eval_root.rglob("*")
        if path.is_file()
        and path != output
        and "__pycache__" not in path.parts
        and "proxy_eval" not in path.parts
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(eval_root).as_posix()}\n" for path in paths),
        encoding="utf-8",
    )
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-root", type=pathlib.Path, default=ROOT)
    parser.add_argument("--write-hashes", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate(args.eval_root)
    reports = args.eval_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    write_json_path = reports / "VALIDATION_REPORT.json"
    write_json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.write_hashes:
        write_hashes(args.eval_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
