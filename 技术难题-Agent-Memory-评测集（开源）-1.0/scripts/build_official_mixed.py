#!/usr/bin/env python3
"""Deterministically rebuild the public 1,000-question Agent Memory pack.

The default output intentionally follows the published reproduction guide:

* LoCoMo session ``date_time`` and multimodal side fields are not injected into
  Add messages.  The omissions are measured separately by ``temporal_audit.py``.
* MemOps is restricted to Remember/Update/Forget/Reflect longitudinal probes.
  The operation quotas reproduce the published 500-question distribution.

This is a public-rule reconstruction.  It is not claimed to be byte-identical
to an unavailable organizer archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
from collections import Counter, defaultdict
from typing import Any, Iterable


ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCOMO_TARGETS = {"1": 167, "2": 167, "4": 166}
LOCOMO_CAT_MAP = {"1": "single_hop", "2": "temporal", "4": "multi_hop"}
MEMOPS_TARGETS = {
    "Remember": 132,
    "Update": 98,
    "Forget": 115,
    "Reflect": 155,
}


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"expected object at {path}:{line_number}")
        rows.append(value)
    return rows


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(path: pathlib.Path) -> str | None:
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            try:
                return subprocess.check_output(
                    ["git", "-C", str(candidate), "rev-parse", "HEAD"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
            except (OSError, subprocess.CalledProcessError):
                return None
    return None


def guide_compatible_locomo_sessions(conv: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert full sessions exactly along the guide-compatible text path."""
    sessions: list[dict[str, Any]] = []
    for session in conv.get("sessions") or []:
        session_id = f"sess-{session.get('session_index', len(sessions) + 1)}"
        messages: list[dict[str, str]] = []
        for turn in session.get("messages") or []:
            text = turn.get("text") or turn.get("content")
            if text is None or not str(text).strip():
                continue
            speaker = turn.get("speaker")
            content = f"{speaker}: {text}" if speaker else str(text)
            messages.append(
                {
                    "role": str(turn.get("role") or "user"),
                    "content": content,
                }
            )
        if messages:
            sessions.append({"session_id": session_id, "messages": messages})
    return sessions


def build_locomo(
    public_dir: pathlib.Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    question_path = public_dir / "questions.jsonl"
    conversation_path = public_dir / "conversations.jsonl"
    questions = load_jsonl(question_path)
    conversations = {
        str(row["sample_id"]): row
        for row in load_jsonl(conversation_path)
        if row.get("sample_id")
    }

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in questions:
        category = str(question.get("category"))
        if (
            category in LOCOMO_TARGETS
            and question.get("question")
            and question.get("answer") is not None
        ):
            by_category[category].append(question)
    for rows in by_category.values():
        rows.sort(
            key=lambda row: (
                str(row.get("sample_id") or ""),
                str(row.get("qa_id") or row.get("qa_index") or ""),
            )
        )

    selected: list[dict[str, Any]] = []
    for category, target in LOCOMO_TARGETS.items():
        available = by_category.get(category, [])
        if len(available) < target:
            raise ValueError(
                f"LoCoMo category {category} has {len(available)} rows; need {target}"
            )
        selected.extend(available[:target])

    by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in selected:
        by_sample[str(question["sample_id"])].append(question)

    samples: list[dict[str, Any]] = []
    flat: list[dict[str, Any]] = []
    for source_id, sample_questions in sorted(by_sample.items()):
        conversation = conversations.get(source_id)
        if conversation is None:
            raise ValueError(f"missing full LoCoMo conversation for {source_id}")
        sessions = guide_compatible_locomo_sessions(conversation)
        if not sessions:
            raise ValueError(f"LoCoMo conversation has no usable sessions: {source_id}")

        search_items: list[dict[str, Any]] = []
        for question in sorted(
            sample_questions,
            key=lambda row: str(row.get("qa_id") or row.get("qa_index") or ""),
        ):
            category = str(question["category"])
            gold = question["answer"]
            item = {
                "qid": str(
                    question.get("qa_id")
                    or f"{source_id}-q{question.get('qa_index')}"
                ),
                "question": str(question["question"]),
                "gold_answer": gold if isinstance(gold, (str, list)) else str(gold),
                "question_type": LOCOMO_CAT_MAP[category],
                "eval_axis": LOCOMO_CAT_MAP[category],
            }
            search_items.append(item)

        sample_id = f"locomo_{source_id}"
        session_ids = [session["session_id"] for session in sessions]
        sample = {
            "dataset": "official",
            "sample_id": sample_id,
            "source": {
                "benchmark": "LoCoMo-Refined",
                "source_id": source_id,
                "add_mode": "full_conversation",
                "conversion_mode": "guide_compat",
                "speaker_a": conversation.get("speaker_a"),
                "speaker_b": conversation.get("speaker_b"),
            },
            "isolation": {
                "user_id": f"eval:locomo:{source_id}",
                "session_ids": session_ids,
            },
            "add_phase": {"sessions": sessions},
            "search_items": search_items,
        }
        samples.append(sample)
        for item in search_items:
            flat.append(
                {
                    "sample_id": sample_id,
                    "user_id": sample["isolation"]["user_id"],
                    "qid": item["qid"],
                    "question": item["question"],
                    "gold_answer": item["gold_answer"],
                    "eval_axis": item["eval_axis"],
                    "benchmark": "LoCoMo-Refined",
                    "session_ids": session_ids,
                    "add_mode": "full_conversation",
                }
            )

    audit = {
        "upstream_questions": len(questions),
        "selected_questions": len(flat),
        "selected_samples": len(samples),
        "selected_qids": [row["qid"] for row in flat],
        "counts_by_axis": dict(sorted(Counter(row["eval_axis"] for row in flat).items())),
    }
    return samples, flat, audit


def memops_sessions(conversations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for index, segment in enumerate(conversations or [], 1):
        segment_index = segment.get("segment_index", index)
        messages: list[dict[str, Any]] = []
        for turn in segment.get("dialogue") or []:
            content = turn.get("content")
            if content is None or not str(content).strip():
                continue
            message: dict[str, Any] = {
                "role": str(turn.get("role") or "user"),
                "content": str(content),
            }
            if turn.get("timestamp") is not None:
                message["timestamp"] = turn["timestamp"]
            messages.append(message)
        if messages:
            sessions.append({"session_id": f"seg-{segment_index}", "messages": messages})
    return sessions


def longitudinal_answers(data: dict[str, Any]) -> list[dict[str, Any]]:
    answers = data.get("answer") or []
    return [
        answer
        for answer in answers
        if answer.get("evaluation_setting") == "longitudinal_operation"
    ]


def select_memops_files(
    inject_dir: pathlib.Path,
) -> tuple[list[tuple[pathlib.Path, dict[str, Any], list[dict[str, Any]]]], dict[str, Any]]:
    """Select deterministic per-operation shards matching the published quotas."""
    candidates: dict[str, list[tuple[pathlib.Path, dict[str, Any]]]] = defaultdict(list)
    all_files = sorted(inject_dir.glob("*.json"), key=lambda path: path.name)
    for path in all_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        operation_type = str(data.get("operation_type") or "")
        if operation_type in MEMOPS_TARGETS:
            candidates[operation_type].append((path, data))

    selected: list[tuple[pathlib.Path, dict[str, Any], list[dict[str, Any]]]] = []
    selection_rows: list[dict[str, Any]] = []
    for operation_type, target in MEMOPS_TARGETS.items():
        remaining = target
        for path, data in candidates.get(operation_type, []):
            answers = longitudinal_answers(data)
            if not answers:
                continue
            chosen = answers[:remaining]
            if chosen:
                selected.append((path, data, chosen))
                selection_rows.append(
                    {
                        "file": path.name,
                        "operation_type": operation_type,
                        "available_questions": len(answers),
                        "selected_questions": len(chosen),
                        "selected_qids": [
                            str(answer.get("question_pair_id") or "")
                            for answer in chosen
                        ],
                    }
                )
                remaining -= len(chosen)
            if remaining == 0:
                break
        if remaining:
            raise ValueError(
                f"MemOps {operation_type} is short by {remaining} longitudinal questions"
            )

    audit = {
        "upstream_json_files": len(all_files),
        "selection_rule": (
            "filter operation_type to Remember/Update/Forget/Reflect; within each "
            "operation sort filename ascending; take longitudinal_operation questions "
            "until the published per-operation quota is met"
        ),
        "targets": MEMOPS_TARGETS,
        "selected_files": selection_rows,
    }
    return selected, audit


def build_memops(
    inject_dir: pathlib.Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    selected, audit = select_memops_files(inject_dir)
    samples: list[dict[str, Any]] = []
    flat: list[dict[str, Any]] = []

    for path, data, answers in selected:
        sessions = memops_sessions(data.get("conversations") or [])
        if not sessions:
            raise ValueError(f"MemOps file has no usable conversations: {path}")
        stem = path.stem
        seen_qids: Counter[str] = Counter()
        search_items: list[dict[str, Any]] = []
        for index, answer in enumerate(answers):
            question = answer.get("question")
            gold = answer.get("expected_answer")
            if not question or gold is None:
                raise ValueError(f"missing MemOps question/gold in {path.name} item {index}")
            base_qid = str(answer.get("question_pair_id") or f"{stem}-q{index}")
            duplicate_index = seen_qids[base_qid]
            seen_qids[base_qid] += 1
            qid = base_qid if duplicate_index == 0 else f"{base_qid}#{duplicate_index}"
            item: dict[str, Any] = {
                "qid": qid,
                "question": str(question),
                "gold_answer": gold if isinstance(gold, (str, list)) else str(gold),
                "eval_axis": (
                    answer.get("evaluation_type")
                    or answer.get("operation_type")
                    or data.get("operation_type")
                ),
            }
            if answer.get("judge_rubric") is not None:
                item["gold_rubric"] = answer["judge_rubric"]
            if answer.get("evaluation_category"):
                item["question_type"] = answer["evaluation_category"]
            # candidate_options is intentionally omitted in guide-compatible mode.
            search_items.append(item)

        sample_id = f"memops_{stem}"
        session_ids = [session["session_id"] for session in sessions]
        sample = {
            "dataset": "official",
            "sample_id": sample_id,
            "source": {
                "benchmark": "MemOps",
                "source_id": path.name,
                "operation_type": data.get("operation_type"),
                "target_fact": data.get("target_fact"),
                "add_mode": "full_conversation",
                "conversion_mode": "guide_compat",
            },
            "isolation": {
                "user_id": f"eval:memops:{stem}",
                "session_ids": session_ids,
            },
            "add_phase": {"sessions": sessions},
            "search_items": search_items,
        }
        samples.append(sample)
        for item in search_items:
            flat.append(
                {
                    "sample_id": sample_id,
                    "user_id": sample["isolation"]["user_id"],
                    "qid": item["qid"],
                    "question": item["question"],
                    "gold_answer": item["gold_answer"],
                    "eval_axis": item["eval_axis"],
                    "benchmark": "MemOps",
                    "operation_type": data.get("operation_type"),
                    "session_ids": session_ids,
                    "gold_rubric": item.get("gold_rubric"),
                    "add_mode": "full_conversation",
                }
            )

    audit["selected_sample_count"] = len(samples)
    audit["selected_question_count"] = len(flat)
    audit["counts_by_operation_type"] = dict(
        sorted(Counter(row["operation_type"] for row in flat).items())
    )
    audit["counts_by_eval_axis"] = dict(
        sorted(Counter(str(row["eval_axis"]) for row in flat).items())
    )
    return samples, flat, audit


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: pathlib.Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")


def build(args: argparse.Namespace) -> dict[str, Any]:
    output_root = args.output_root.resolve()
    official = output_root / "official"
    samples_dir = official / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    locomo_samples, locomo_flat, locomo_audit = build_locomo(args.locomo_public)
    memops_samples, memops_flat, memops_audit = build_memops(args.memops_inject)
    flat = locomo_flat + memops_flat
    flat.sort(key=lambda row: (row["benchmark"], row["sample_id"], row["qid"]))
    samples = sorted(locomo_samples + memops_samples, key=lambda row: row["sample_id"])

    if len(flat) != 1000:
        raise ValueError(f"expected 1000 questions, got {len(flat)}")
    if len(samples) != 110:
        raise ValueError(f"expected 110 samples, got {len(samples)}")

    expected_names = {f"{sample['sample_id']}.json" for sample in samples}
    for existing in samples_dir.glob("*.json"):
        if existing.name not in expected_names:
            existing.unlink()
    for sample in samples:
        write_json(samples_dir / f"{sample['sample_id']}.json", sample)
    write_jsonl(official / "questions.jsonl", flat)

    benchmark_counts = Counter(row["benchmark"] for row in flat)
    axis_counts = Counter(str(row.get("eval_axis") or "unknown") for row in flat)
    operation_counts = Counter(
        str(row["operation_type"])
        for row in flat
        if row.get("operation_type")
    )
    locomo_axis_counts = Counter(
        str(row["eval_axis"])
        for row in flat
        if row["benchmark"] == "LoCoMo-Refined"
    )
    manifest = {
        "version": "1.0-official-mixed-public-reconstruction",
        "reconstruction_status": "public-rule reconstruction; not organizer-byte-verified",
        "cap": 1000,
        "search_items": len(flat),
        "samples": len(samples),
        "counts_by_benchmark": dict(sorted(benchmark_counts.items())),
        "counts_by_eval_axis": dict(sorted(axis_counts.items())),
        "counts_by_memops_operation_type": dict(sorted(operation_counts.items())),
        "counts_by_locomo_axis": dict(sorted(locomo_axis_counts.items())),
        "locomo": {
            "source": "LoCoMo_refined/data/public",
            "commit": git_commit(args.locomo_public),
            "add_mode": "full_conversation",
            "conversion_mode": "guide_compat",
            "excluded_categories": ["3", "5"],
            "preferred_categories": ["1", "2", "4"],
            "target": 500,
            "actual": benchmark_counts.get("LoCoMo-Refined", 0),
        },
        "memops": {
            "source": "MemOps/generated_result/4-inject_evidence_with_distractors",
            "commit": git_commit(args.memops_inject),
            "add_mode": "full_conversation",
            "filter": (
                "evaluation_setting=longitudinal_operation; operation_type in "
                "Remember/Update/Forget/Reflect; published per-operation quotas"
            ),
            "target": 500,
            "actual": benchmark_counts.get("MemOps", 0),
        },
        "notes": [
            "Guide-compatible main pack: LoCoMo session date_time is intentionally not copied into Add messages.",
            "Guide-compatible main pack: LoCoMo multimodal side fields and MemOps candidate_options are intentionally omitted.",
            "See reports/temporal_audit.json and reports/data_quality_audit.json before interpreting temporal or option-based results.",
            "Deterministic order: (benchmark, sample_id, qid).",
        ],
    }
    write_json(official / "manifest.json", manifest)

    source_lock = {
        "reconstruction_type": "public-rule",
        "locomo": {
            "repository": "https://github.com/mem-eval-suite/LoCoMo_refined",
            "commit": git_commit(args.locomo_public),
            "questions_jsonl_sha256": sha256_file(args.locomo_public / "questions.jsonl"),
            "conversations_jsonl_sha256": sha256_file(args.locomo_public / "conversations.jsonl"),
        },
        "memops": {
            "repository": "https://github.com/MemTensor/MemOps",
            "commit": git_commit(args.memops_inject),
            "upstream_file_count": len(list(args.memops_inject.glob("*.json"))),
            "selected_files": [
                {
                    "file": row["file"],
                    "sha256": sha256_file(args.memops_inject / row["file"]),
                    "selected_questions": row["selected_questions"],
                    "selected_qids": row["selected_qids"],
                }
                for row in memops_audit["selected_files"]
            ],
        },
    }
    write_json(output_root / "SOURCE_LOCK.json", source_lock)
    write_json(
        output_root / "reports" / "build_selection.json",
        {"locomo": locomo_audit, "memops": memops_audit},
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--locomo-public",
        type=pathlib.Path,
        required=True,
        help="Path to LoCoMo_refined/data/public",
    )
    parser.add_argument(
        "--memops-inject",
        type=pathlib.Path,
        required=True,
        help="Path to MemOps/generated_result/4-inject_evidence_with_distractors",
    )
    parser.add_argument(
        "--output-root",
        type=pathlib.Path,
        default=ROOT,
        help="Evaluation package root (defaults to the parent of scripts/)",
    )
    args = parser.parse_args()
    if not args.locomo_public.is_dir():
        parser.error(f"LoCoMo public directory not found: {args.locomo_public}")
    if not args.memops_inject.is_dir():
        parser.error(f"MemOps inject directory not found: {args.memops_inject}")
    return args


def main() -> int:
    manifest = build(parse_args())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
