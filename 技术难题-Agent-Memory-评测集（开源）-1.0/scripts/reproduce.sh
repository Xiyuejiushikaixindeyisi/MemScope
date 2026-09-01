#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 /path/to/LoCoMo_refined/data/public /path/to/MemOps/generated_result/4-inject_evidence_with_distractors" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVAL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCOMO_PUBLIC="$1"
MEMOPS_INJECT="$2"

python3 "$SCRIPT_DIR/build_official_mixed.py" \
  --locomo-public "$LOCOMO_PUBLIC" \
  --memops-inject "$MEMOPS_INJECT" \
  --output-root "$EVAL_ROOT"
python3 "$SCRIPT_DIR/temporal_audit.py" \
  --eval-root "$EVAL_ROOT" \
  --locomo-public "$LOCOMO_PUBLIC" \
  --memops-inject "$MEMOPS_INJECT"
python3 "$SCRIPT_DIR/validate_pack.py" --eval-root "$EVAL_ROOT" --write-hashes
