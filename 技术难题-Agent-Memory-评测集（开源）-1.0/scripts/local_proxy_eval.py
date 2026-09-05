#!/usr/bin/env python3
"""Run the Add/Search protocol and score it with a non-official local proxy.

The proxy is deliberately deterministic and dependency-free:

* Proxy Answer selects the most query-relevant returned evidence sentences.
* Proxy Judge uses normalized containment, token F1, and MemOps rubric phrases.

It is useful for regression testing retrieval changes.  It is NOT the organizer
Answer/Judge and its accuracy must never be reported as an official score.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import re
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Iterable


ROOT = pathlib.Path(__file__).resolve().parents[1]
PROXY_NAME = "deterministic-extractive-proxy-v1"
MAX_RESPONSE_BYTES = 2_000_000
TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "she",
    "should",
    "that",
    "the",
    "their",
    "them",
    "they",
    "this",
    "to",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
}


def load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def write_jsonl(path: pathlib.Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    path.chmod(0o600)


def prepare_sensitive_output(output_dir: pathlib.Path, eval_root: pathlib.Path) -> pathlib.Path:
    if output_dir.is_symlink():
        raise ValueError("--output-dir must not be a symbolic link")
    output = output_dir.expanduser().resolve()
    source = eval_root.expanduser().resolve()
    try:
        output.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError("--output-dir must be outside the evaluation source tree")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("--output-dir must be a real directory")
    return output


def tokens(text: Any, *, drop_stopwords: bool = False) -> list[str]:
    values = [match.group(0).lower() for match in TOKEN_RE.finditer(str(text or ""))]
    if drop_stopwords:
        return [value for value in values if value not in STOPWORDS]
    return values


def normalize(text: Any) -> str:
    return " ".join(tokens(text))


def token_f1(reference: str, candidate: str) -> float:
    ref = Counter(tokens(reference))
    pred = Counter(tokens(candidate))
    if not ref or not pred:
        return 0.0
    overlap = sum((ref & pred).values())
    precision = overlap / sum(pred.values())
    recall = overlap / sum(ref.values())
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def evidence_segments(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for rank, memory in enumerate(memories, 1):
        content = str(memory.get("content") or "").strip()
        if not content:
            continue
        parts = [part.strip() for part in SENTENCE_RE.split(content) if part.strip()]
        if not parts:
            parts = [content]
        for position, part in enumerate(parts):
            segments.append(
                {
                    "text": part,
                    "memory_id": str(memory.get("id") or f"rank-{rank}"),
                    "memory_rank": rank,
                    "position": position,
                }
            )
    return segments


def segment_score(question: str, segment: dict[str, Any]) -> float:
    query_tokens = tokens(question, drop_stopwords=True)
    text_tokens = tokens(segment["text"])
    if not text_tokens:
        return -math.inf
    query_counts = Counter(query_tokens)
    text_counts = Counter(text_tokens)
    overlap = sum((query_counts & text_counts).values())
    coverage = overlap / max(1, len(query_counts))
    rarity_bonus = sum(
        1.0 / (1.0 + query_counts[token]) for token in text_counts if token in query_counts
    )
    rank_bonus = 1.0 / max(1, int(segment["memory_rank"]))
    number_bonus = 0.75 * len(
        {token for token in query_counts if token.isdigit()} & set(text_counts)
    )
    return 4.0 * coverage + rarity_bonus + rank_bonus + number_bonus


def choose_option(options: list[str], evidence: str) -> str:
    evidence_tokens = Counter(tokens(evidence))
    scored: list[tuple[float, int, str]] = []
    for index, option in enumerate(options):
        option_tokens = Counter(tokens(option, drop_stopwords=True))
        overlap = sum((option_tokens & evidence_tokens).values())
        coverage = overlap / max(1, sum(option_tokens.values()))
        scored.append((coverage, -index, option))
    return max(scored)[2] if scored else ""


def proxy_answer(
    question: str,
    memories: list[dict[str, Any]],
    options: list[str] | None = None,
    *,
    max_segments: int = 3,
    max_characters: int = 1200,
) -> dict[str, Any]:
    segments = evidence_segments(memories)
    ranked = sorted(
        segments,
        key=lambda segment: (
            -segment_score(question, segment),
            int(segment["memory_rank"]),
            int(segment["position"]),
            str(segment["memory_id"]),
        ),
    )
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    size = 0
    for segment in ranked:
        key = normalize(segment["text"])
        if not key or key in seen:
            continue
        projected = size + len(segment["text"]) + (1 if chosen else 0)
        if chosen and projected > max_characters:
            continue
        chosen.append(segment)
        seen.add(key)
        size = projected
        if len(chosen) >= max_segments:
            break
    evidence = " ".join(str(segment["text"]) for segment in chosen)
    answer = choose_option(options, evidence) if options else evidence
    return {
        "answer": answer,
        "selected_evidence": chosen,
        "proxy_answer_name": PROXY_NAME,
    }


def gold_candidates(gold: Any) -> list[str]:
    if isinstance(gold, list):
        return [str(value) for value in gold if str(value).strip()]
    return [str(gold)] if str(gold).strip() else []


def phrase_present(phrase: str, answer: str) -> bool:
    phrase_norm = normalize(phrase)
    answer_norm = normalize(answer)
    return bool(phrase_norm) and phrase_norm in answer_norm


def numeric_conflict(gold: str, answer: str) -> bool:
    gold_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", gold))
    answer_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", answer))
    return bool(gold_numbers and answer_numbers and not gold_numbers.issubset(answer_numbers))


def proxy_judge(
    question: str,
    gold: Any,
    answer: str,
    rubric: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = gold_candidates(gold)
    answer_norm = normalize(answer)
    candidate_metrics: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_norm = normalize(candidate)
        f1 = token_f1(candidate, answer)
        candidate_metrics.append(
            {
                "gold": candidate,
                "exact": candidate_norm == answer_norm and bool(candidate_norm),
                "gold_contained": bool(candidate_norm) and candidate_norm in answer_norm,
                "token_f1": f1,
                "numeric_conflict": numeric_conflict(candidate, answer),
            }
        )

    best = max(
        candidate_metrics,
        key=lambda row: (bool(row["exact"]), bool(row["gold_contained"]), row["token_f1"]),
        default={
            "exact": False,
            "gold_contained": False,
            "token_f1": 0.0,
            "numeric_conflict": False,
        },
    )
    base_correct = bool(best["exact"] or best["gold_contained"] or best["token_f1"] >= 0.72)
    if best.get("numeric_conflict"):
        base_correct = False

    rubric = rubric if isinstance(rubric, dict) else {}
    must_include = [str(value) for value in rubric.get("must_include") or []]
    must_not_include = [str(value) for value in rubric.get("must_not_include") or []]
    include_hits = [value for value in must_include if phrase_present(value, answer)]
    forbidden_hits = [value for value in must_not_include if phrase_present(value, answer)]
    if must_include and len(include_hits) == len(must_include) and not forbidden_hits:
        base_correct = True
    if forbidden_hits:
        base_correct = False

    return {
        "score": int(base_correct),
        "official": False,
        "proxy_judge_name": PROXY_NAME,
        "best_gold_match": best,
        "must_include_count": len(must_include),
        "must_include_hits": include_hits,
        "must_not_include_hits": forbidden_hits,
        "warning": "Non-official deterministic proxy; not comparable to organizer scores.",
    }


@dataclass
class HttpClient:
    base_url: str
    timeout: float
    auth_mode: str = "none"
    credential: str | None = None
    min_interval_seconds: float = 0.0
    max_rate_limit_retries: int = 4
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 8.0
    rate_limit_retries: int = dataclass_field(default=0, init=False)
    _last_request_started: float = dataclass_field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        origin = self.base_url.rstrip("/")
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base URL must be an HTTP(S) origin without credentials or query")
        if self.auth_mode not in {"none", "bearer", "token", "x-api-key"}:
            raise ValueError("unsupported auth mode")
        if self.auth_mode == "none" and self.credential:
            raise ValueError("credential was supplied while auth mode is none")
        if self.auth_mode != "none" and not self.credential:
            raise ValueError("selected auth mode requires the configured credential environment")
        if self.timeout <= 0 or self.min_interval_seconds < 0:
            raise ValueError("timeouts and request intervals must be non-negative")
        if self.max_rate_limit_retries < 0:
            raise ValueError("rate-limit retries must be non-negative")
        self.base_url = origin

    def _throttle(self) -> None:
        remaining = self.min_interval_seconds - (time.monotonic() - self._last_request_started)
        if remaining > 0:
            time.sleep(remaining)

    def _authorization_headers(self) -> dict[str, str]:
        if self.auth_mode == "bearer":
            return {"Authorization": f"Bearer {self.credential}"}
        if self.auth_mode == "token":
            return {"Authorization": f"Token {self.credential}"}
        if self.auth_mode == "x-api-key":
            return {"X-Api-Key": str(self.credential)}
        return {}

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        *,
        timeout: float | None = None,
    ) -> tuple[int, Any, float]:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        headers.update(self._authorization_headers())
        request = urllib.request.Request(  # noqa: S310 -- base URL is restricted to HTTP(S).
            url, data=body, headers=headers, method=method
        )
        started = time.monotonic()
        request_timeout = self.timeout if timeout is None else min(self.timeout, timeout)
        for attempt in range(self.max_rate_limit_retries + 1):
            self._throttle()
            self._last_request_started = time.monotonic()
            try:
                with urllib.request.urlopen(  # noqa: S310 -- validated HTTP(S) request.
                    request, timeout=request_timeout
                ) as response:
                    raw_bytes = response.read(MAX_RESPONSE_BYTES + 1)
                    status = response.status
                break
            except urllib.error.HTTPError as exc:
                raw_bytes = exc.read(MAX_RESPONSE_BYTES + 1)
                if exc.code == 429 and attempt < self.max_rate_limit_retries:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        requested_wait = float(retry_after) if retry_after is not None else 0.0
                    except ValueError:
                        requested_wait = 0.0
                    backoff = min(
                        self.max_backoff_seconds,
                        max(requested_wait, self.initial_backoff_seconds * (2**attempt)),
                    )
                    self.rate_limit_retries += 1
                    time.sleep(backoff)
                    continue
                raise RuntimeError(f"HTTP {exc.code} for {method} {path}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"request transport failed for {method} {path}") from exc
            except TimeoutError as exc:
                raise RuntimeError(f"request timed out for {method} {path}") from exc
        else:  # pragma: no cover - the bounded loop always returns or raises
            raise RuntimeError(f"request retry state failed for {method} {path}")
        latency = time.monotonic() - started
        if len(raw_bytes) > MAX_RESPONSE_BYTES:
            raise RuntimeError(f"oversized response for {method} {path}")
        try:
            raw = raw_bytes.decode("utf-8")
            decoded = json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"non-JSON response for {method} {path}") from exc
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"non-UTF-8 response for {method} {path}") from exc
        return status, decoded, latency


def chunk_messages(
    messages: list[dict[str, Any]],
    *,
    max_messages: int = 20,
    max_words: int = 2000,
) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_words = 0
    for message in messages:
        word_count = len(str(message.get("content") or "").split())
        exceeds = current and (
            len(current) >= max_messages or current_words + word_count > max_words
        )
        if exceeds:
            chunks.append(current)
            current = []
            current_words = 0
        current.append(message)
        current_words += word_count
    if current:
        chunks.append(current)
    return chunks


def validate_add_response(response: Any, request: dict[str, Any]) -> None:
    if not isinstance(response, dict) or response.get("success") is not True:
        raise ValueError(f"invalid Add response: {response!r}")
    for field in ("request_id", "user_id", "session_id"):
        if response.get(field) != request[field]:
            raise ValueError(f"Add response {field} mismatch: {response!r}")


def validate_search_response(response: Any, top_k: int) -> list[dict[str, Any]]:
    if not isinstance(response, dict) or not isinstance(response.get("data"), list):
        raise ValueError(f"invalid Search response envelope: {response!r}")
    data = cast("list[dict[str, Any]]", response["data"])
    if len(data) > top_k:
        raise ValueError(f"Search returned {len(data)} rows for top_k={top_k}")
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Search data[{index}] is not an object")
        if not isinstance(item.get("id"), str) or not item["id"].strip():
            raise ValueError(f"Search data[{index}].id must be a non-empty string")
        if not isinstance(item.get("content"), str) or not item["content"].strip():
            raise ValueError(f"Search data[{index}].content must be a non-empty string")
    return data


def run_service(args: argparse.Namespace) -> pathlib.Path:
    output_dir = cast("pathlib.Path", args.output_dir)
    credential = os.getenv(args.credential_env) if args.auth_mode != "none" else None
    client = HttpClient(
        args.base_url,
        args.timeout,
        auth_mode=args.auth_mode,
        credential=credential,
        min_interval_seconds=args.min_interval_seconds,
        max_rate_limit_retries=args.max_rate_limit_retries,
        initial_backoff_seconds=args.initial_backoff_seconds,
        max_backoff_seconds=args.max_backoff_seconds,
    )
    health_status, _, _ = client.request("GET", args.health_path, timeout=10)
    if not 200 <= health_status < 300:
        raise RuntimeError(f"health returned HTTP {health_status}")

    sample_paths = sorted((args.eval_root / "official" / "samples").glob("*.json"))
    if args.max_samples is not None:
        sample_paths = sample_paths[: args.max_samples]
    run_id = args.run_id or f"proxy-{uuid.uuid4().hex[:12]}"
    rows: list[dict[str, Any]] = []
    add_latencies: list[float] = []
    search_latencies: list[float] = []

    for sample_path in sample_paths:
        sample = load_json(sample_path)
        user_id = f"{run_id}:{sample['isolation']['user_id']}"
        for session in sample["add_phase"]["sessions"]:
            session_id = f"{run_id}:{sample['sample_id']}:{session['session_id']}"
            for chunk_index, chunk in enumerate(chunk_messages(session["messages"])):
                request = {
                    "request_id": (
                        f"{run_id}:{sample['sample_id']}:{session['session_id']}:"
                        f"chunk-{chunk_index}"
                    ),
                    "user_id": user_id,
                    "session_id": session_id,
                    "messages": chunk,
                }
                status, response, latency = client.request(
                    "POST", args.add_path, request, timeout=119
                )
                if status != 200:
                    raise RuntimeError(f"Add returned HTTP {status}")
                validate_add_response(response, request)
                add_latencies.append(latency)

        for item in sample["search_items"]:
            request = {
                "query": item["question"],
                "user_id": user_id,
                "top_k": args.top_k,
            }
            if item.get("options"):
                request["options"] = item["options"]
            status, response, latency = client.request(
                "POST", args.search_path, request, timeout=59
            )
            if status != 200:
                raise RuntimeError(f"Search returned HTTP {status}")
            data = validate_search_response(response, args.top_k)
            search_latencies.append(latency)
            rows.append(
                {
                    "sample_id": sample["sample_id"],
                    "qid": item["qid"],
                    "benchmark": sample["source"]["benchmark"],
                    "operation_type": sample["source"].get("operation_type"),
                    "eval_axis": item.get("eval_axis"),
                    "question": item["question"],
                    "options": item.get("options"),
                    "gold_answer": item["gold_answer"],
                    "gold_rubric": item.get("gold_rubric"),
                    "search_data": data,
                    "search_latency_seconds": latency,
                }
            )

    output = output_dir / "search_results.jsonl"
    write_jsonl(output, rows)
    write_json(
        output_dir / "protocol_summary.json",
        {
            "official": False,
            "run_id": run_id,
            "samples": len(sample_paths),
            "questions": len(rows),
            "add_calls": len(add_latencies),
            "rate_limit_retries": client.rate_limit_retries,
            "mean_add_latency_seconds": sum(add_latencies) / len(add_latencies)
            if add_latencies
            else None,
            "mean_search_latency_seconds": sum(search_latencies) / len(search_latencies)
            if search_latencies
            else None,
        },
    )
    return output


def summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    correct = sum(int(row["proxy_judge"]["score"]) for row in rows)
    return {"total": total, "correct": correct, "accuracy": correct / total if total else 0.0}


def score_results(input_path: pathlib.Path, output_dir: pathlib.Path) -> dict[str, Any]:
    rows = load_jsonl(input_path)
    scored: list[dict[str, Any]] = []
    for row in rows:
        answer = proxy_answer(
            str(row["question"]),
            row.get("search_data") or [],
            row.get("options"),
        )
        judge = proxy_judge(
            str(row["question"]),
            row.get("gold_answer"),
            str(answer["answer"]),
            row.get("gold_rubric"),
        )
        scored.append({**row, "proxy_answer": answer, "proxy_judge": judge})

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
        "benchmark": defaultdict(list),
        "operation_type": defaultdict(list),
        "eval_axis": defaultdict(list),
    }
    for row in scored:
        for field in grouped:
            value = row.get(field)
            if value not in (None, ""):
                grouped[field][str(value)].append(row)
    summary = {
        "official": False,
        "proxy_name": PROXY_NAME,
        "warning": "This is a local proxy score and is not comparable to the organizer score.",
        "input": str(input_path),
        "overall": summarize_group(scored),
        "by_benchmark": {
            key: summarize_group(value) for key, value in sorted(grouped["benchmark"].items())
        },
        "by_operation_type": {
            key: summarize_group(value) for key, value in sorted(grouped["operation_type"].items())
        },
        "by_eval_axis": {
            key: summarize_group(value) for key, value in sorted(grouped["eval_axis"].items())
        },
    }
    write_jsonl(output_dir / "proxy_scored.jsonl", scored)
    write_json(output_dir / "proxy_summary.json", summary)
    return summary


def self_test() -> None:
    memories = [
        {"id": "m1", "content": "Caroline went to the support group yesterday."},
        {"id": "m2", "content": "Melanie painted a sunrise in 2022."},
    ]
    answer = proxy_answer("When did Melanie paint a sunrise?", memories)
    if "2022" not in answer["answer"]:
        raise RuntimeError("proxy self-test answer failed")
    judge = proxy_judge("When?", ["2022"], answer["answer"])
    if judge["score"] != 1:
        raise RuntimeError("proxy self-test judge failed")
    chunks = chunk_messages([{"content": "x"}] * 21)
    if [len(chunk) for chunk in chunks] != [20, 1]:
        raise RuntimeError("proxy self-test chunking failed")
    print(json.dumps({"self_test": "ok", "proxy_name": PROXY_NAME}))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-root", type=pathlib.Path, default=ROOT)
    parser.add_argument("--input-results", type=pathlib.Path)
    parser.add_argument("--base-url")
    parser.add_argument("--health-path", default="/health")
    parser.add_argument("--add-path", default="/add")
    parser.add_argument("--search-path", default="/search")
    parser.add_argument(
        "--auth-mode", choices=("none", "bearer", "token", "x-api-key"), default="none"
    )
    parser.add_argument("--credential-env", default="MEMSCOPE_EVAL_API_KEY")
    parser.add_argument("--timeout", type=float, default=119.0)
    parser.add_argument("--min-interval-seconds", type=float, default=0.0)
    parser.add_argument("--max-rate-limit-retries", type=int, default=4)
    parser.add_argument("--initial-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--max-backoff-seconds", type=float, default=8.0)
    parser.add_argument("--top-k", type=int, default=100)
    parser.add_argument("--max-samples", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--output-dir", type=pathlib.Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test and not args.input_results and not args.base_url:
        parser.error(
            "provide --base-url to run a service, or --input-results to score "
            "captured Search results"
        )
    if not args.self_test and args.output_dir is None:
        parser.error("--output-dir outside the evaluation source tree is required")
    if not 1 <= args.top_k <= 100:
        parser.error("--top-k must be between 1 and 100")
    if args.timeout <= 0 or args.min_interval_seconds < 0:
        parser.error("--timeout must be positive and --min-interval-seconds non-negative")
    if args.max_rate_limit_retries < 0:
        parser.error("--max-rate-limit-retries must be non-negative")
    if args.initial_backoff_seconds <= 0 or args.max_backoff_seconds <= 0:
        parser.error("backoff values must be positive")
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.credential_env) is None:
        parser.error("--credential-env must be an environment-variable name")
    return args


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output_dir is None:
        raise RuntimeError("validated output directory is unexpectedly absent")
    args.output_dir = prepare_sensitive_output(args.output_dir, args.eval_root)
    input_path = args.input_results
    if args.base_url:
        input_path = run_service(args)
    if input_path is None:
        raise RuntimeError("validated proxy input is unexpectedly absent")
    summary = score_results(input_path, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
