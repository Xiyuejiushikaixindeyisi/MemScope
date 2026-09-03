#!/bin/sh
set -eu

: "${DATABASE_PATH:=/var/lib/memscope/raw.db}"
: "${MEMOS_GATEWAY_RECEIPT_PATH:=/var/lib/memscope/gateway-receipts.db}"

mkdir -p "$(dirname "${DATABASE_PATH}")" "$(dirname "${MEMOS_GATEWAY_RECEIPT_PATH}")"
test -w "$(dirname "${DATABASE_PATH}")"
test -w "$(dirname "${MEMOS_GATEWAY_RECEIPT_PATH}")"

exec "$@"
