#!/usr/bin/env python3
"""Audit information intentionally omitted by the guide-compatible converter."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import Counter
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
RELATIVE_TIME = re.compile(
    r"\b(yesterday|today|tomorrow|last\s+(?:night|week|month|year|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"next\s+(?:week|month|year|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday)|ago|earlier|recently|the\s+previous\s+day)\b",
    re.IGNORECASE,
)


def load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def selected_qids(eval_root: pathlib.Path) -> set[str]:
    return {
        str(row["qid"])
        for row in load_jsonl(eval_root / "official" / "questions.jsonl")
        if row.get("benchmark") == "LoCoMo-Refined"
    }


def audit_temporal(eval_root: pathlib.Path, locomo_public: pathlib.Path) -> dict[str, Any]:
    selected = selected_qids(eval_root)
    questions = {
        str(row.get("qa_id")): row
        for row in load_jsonl(locomo_public / "questions.jsonl")
        if row.get("qa_id")
    }
    conversations = {
        str(row["sample_id"]): row
        for row in load_jsonl(locomo_public / "conversations.jsonl")
        if row.get("sample_id")
    }

    sample_contents: dict[str, str] = {}
    for path in (eval_root / "official" / "samples").glob("locomo_*.json"):
        sample = load_json(path)
        sample_contents[str(sample["source"]["source_id"])] = "\n".join(
            str(message["content"])
            for session in sample["add_phase"]["sessions"]
            for message in session["messages"]
        )

    details: list[dict[str, Any]] = []
    session_dates_total = 0
    session_dates_copied = 0
    relative_evidence_count = 0
    multimodal_selected_count = 0
    multimodal_evidence_count = 0

    for qid in sorted(selected):
        question = questions[qid]
        source_id = str(question["sample_id"])
        conversation = conversations[source_id]
        sessions = conversation.get("sessions") or []
        dates = [str(session.get("date_time")) for session in sessions if session.get("date_time")]
        session_dates_total += len(dates)
        guide_content = sample_contents[source_id]
        copied_dates = [date for date in dates if date in guide_content]
        session_dates_copied += len(copied_dates)

        evidence_messages = question.get("evidence_messages") or []
        evidence_text = "\n".join(
            str(message.get("text") or message.get("content") or "")
            for message in evidence_messages
        )
        has_relative_evidence = bool(RELATIVE_TIME.search(evidence_text))
        if str(question.get("category")) == "2" and has_relative_evidence:
            relative_evidence_count += 1
        evidence_is_multimodal = any(
            bool(message.get("has_multimodal_context"))
            or bool(message.get("images"))
            or bool(message.get("blip_caption"))
            or bool(message.get("query"))
            for message in evidence_messages
        )
        if evidence_is_multimodal:
            multimodal_evidence_count += 1
        if bool(question.get("is_multi_modality")):
            multimodal_selected_count += 1

        if str(question.get("category")) == "2":
            details.append(
                {
                    "qid": qid,
                    "sample_id": source_id,
                    "question": question.get("question"),
                    "gold_answer": question.get("answer"),
                    "session_dates_available": dates,
                    "session_dates_present_verbatim_in_guide_content": copied_dates,
                    "evidence_contains_relative_time": has_relative_evidence,
                    "evidence_message_count": len(evidence_messages),
                    "evidence_is_multimodal": evidence_is_multimodal,
                }
            )

    temporal_details = [row for row in details]
    return {
        "status": "audit-only; main pack was not modified",
        "conversion_mode": "guide_compat",
        "selected_locomo_questions": len(selected),
        "selected_temporal_questions": len(temporal_details),
        "selected_temporal_questions_with_relative_time_in_evidence": relative_evidence_count,
        "selected_multimodal_questions": multimodal_selected_count,
        "selected_questions_with_multimodal_evidence": multimodal_evidence_count,
        "upstream_session_date_values_across_selected_samples_and_questions": session_dates_total,
        "session_date_values_copied_verbatim_into_guide_content": session_dates_copied,
        "interpretation": (
            "The guide-compatible converter omits session date_time. Temporal questions "
            "whose evidence uses relative expressions may therefore lose the calendar "
            "anchor required to reproduce an absolute gold date. Counts over session "
            "dates are question-weighted because each selected question is audited."
        ),
        "temporal_questions": temporal_details,
    }


def audit_memops_options(eval_root: pathlib.Path, memops_inject: pathlib.Path) -> dict[str, Any]:
    selection = load_json(eval_root / "reports" / "build_selection.json")["memops"]
    sample_by_id = {
        path.stem: load_json(path)
        for path in (eval_root / "official" / "samples").glob("memops_*.json")
    }
    selected_with_options = 0
    omitted_options = 0
    examples: list[dict[str, Any]] = []
    for file_row in selection["selected_files"]:
        source = load_json(memops_inject / file_row["file"])
        selected_ids = Counter(str(value) for value in file_row["selected_qids"])
        sample = sample_by_id[f"memops_{pathlib.Path(file_row['file']).stem}"]
        output_items = {str(item["qid"]): item for item in sample["search_items"]}
        for answer in source.get("answer") or []:
            qid = str(answer.get("question_pair_id") or "")
            if selected_ids[qid] <= 0:
                continue
            selected_ids[qid] -= 1
            options = answer.get("candidate_options")
            if not options:
                continue
            selected_with_options += 1
            output = output_items.get(qid, {})
            if "options" not in output:
                omitted_options += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "source_file": file_row["file"],
                        "qid": qid,
                        "question": answer.get("question"),
                        "candidate_options_count": len(options),
                        "options_present_in_main_pack": "options" in output,
                    }
                )
    return {
        "status": "audit-only; main pack was not modified",
        "selected_memops_questions_with_upstream_candidate_options": selected_with_options,
        "candidate_option_fields_omitted_by_guide_compatible_converter": omitted_options,
        "interpretation": (
            "The published guide converter does not copy candidate_options to the sample "
            "options field. This report records the omission without silently correcting it."
        ),
        "examples": examples,
    }


def markdown_report(temporal: dict[str, Any], quality: dict[str, Any]) -> str:
    return f"""# Guide-compatible data audit

This report is diagnostic only. The main evaluation pack was not modified.

## Temporal information

- Selected LoCoMo questions: {temporal['selected_locomo_questions']}
- Selected temporal questions: {temporal['selected_temporal_questions']}
- Temporal questions whose evidence contains relative-time language: {temporal['selected_temporal_questions_with_relative_time_in_evidence']}
- Session date values copied verbatim into Add content: {temporal['session_date_values_copied_verbatim_into_guide_content']}

The guide-compatible converter omits upstream `session.date_time`. Relative expressions
such as “yesterday” may therefore lose the calendar anchor needed for an absolute date.

## Other omitted upstream context

- Selected multimodal LoCoMo questions: {temporal['selected_multimodal_questions']}
- Selected questions with multimodal evidence: {temporal['selected_questions_with_multimodal_evidence']}
- Selected MemOps questions with candidate options upstream: {quality['selected_memops_questions_with_upstream_candidate_options']}
- Candidate-option fields omitted in the main pack: {quality['candidate_option_fields_omitted_by_guide_compatible_converter']}

These are compatibility findings, not silent corrections. See the JSON reports for details.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-root", type=pathlib.Path, default=ROOT)
    parser.add_argument("--locomo-public", type=pathlib.Path, required=True)
    parser.add_argument("--memops-inject", type=pathlib.Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    temporal = audit_temporal(args.eval_root, args.locomo_public)
    quality = audit_memops_options(args.eval_root, args.memops_inject)
    reports = args.eval_root / "reports"
    write_json(reports / "temporal_audit.json", temporal)
    write_json(reports / "data_quality_audit.json", quality)
    (reports / "DATA_QUALITY_AUDIT.md").write_text(
        markdown_report(temporal, quality), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "temporal": {
                    "selected_temporal_questions": temporal["selected_temporal_questions"],
                    "relative_time_evidence": temporal[
                        "selected_temporal_questions_with_relative_time_in_evidence"
                    ],
                    "session_dates_copied": temporal[
                        "session_date_values_copied_verbatim_into_guide_content"
                    ],
                },
                "data_quality": {
                    "selected_multimodal_questions": temporal[
                        "selected_multimodal_questions"
                    ],
                    "candidate_options_omitted": quality[
                        "candidate_option_fields_omitted_by_guide_compatible_converter"
                    ],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
