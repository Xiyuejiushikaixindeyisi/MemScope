#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8080}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAMPLE="$ROOT_DIR/smoke/sample_locomo_style.json"

curl -fsS "$BASE_URL/health"
python3 - "$SAMPLE" "$BASE_URL" <<'PY'
import json, pathlib, subprocess, sys
sample = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
base = sys.argv[2].rstrip("/")
session = sample["add_phase"]["sessions"][0]
add = {
    "request_id": "smoke:locomo:chunk-0",
    "user_id": sample["isolation"]["user_id"],
    "session_id": session["session_id"],
    "messages": session["messages"],
}
subprocess.run(["curl", "-fsS", "-H", "Content-Type: application/json", "-d", json.dumps(add), f"{base}/add"], check=True)
item = sample["search_items"][0]
search = {"query": item["question"], "user_id": sample["isolation"]["user_id"], "top_k": 100}
subprocess.run(["curl", "-fsS", "-H", "Content-Type: application/json", "-d", json.dumps(search), f"{base}/search"], check=True)
PY
