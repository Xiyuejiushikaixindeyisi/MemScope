#!/bin/sh
set -eu

: "${MEMOS_BASE_PATH:=/var/lib/memos}"
: "${FILE_LOCAL_PATH:=${MEMOS_BASE_PATH}/files}"

mkdir -p "${MEMOS_BASE_PATH}" "${FILE_LOCAL_PATH}"
test -w "${MEMOS_BASE_PATH}"
test -w "${FILE_LOCAL_PATH}"

exec "$@"
