#!/bin/sh
set -eu

: "${MEMOS_BASE_PATH:=/var/lib/memos}"
: "${FILE_LOCAL_PATH:=${MEMOS_BASE_PATH}/files}"
: "${MEMSCOPE_MODEL_PROFILE:?set MEMSCOPE_MODEL_PROFILE to gateway or mock}"
: "${MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP:=false}"
: "${MEMRADER_MODEL:?set MEMRADER_MODEL}"
: "${MEMRADER_API_BASE:?set MEMRADER_API_BASE}"
: "${MEMRADER_API_KEY:?set MEMRADER_API_KEY}"
: "${MOS_EMBEDDER_MODEL:?set MOS_EMBEDDER_MODEL}"
: "${MOS_EMBEDDER_API_BASE:?set MOS_EMBEDDER_API_BASE}"
: "${MOS_EMBEDDER_API_KEY:?set MOS_EMBEDDER_API_KEY}"
: "${EMBEDDING_DIMENSION:?set EMBEDDING_DIMENSION}"

case "${MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP}" in
    true|false) ;;
    *) exit 64 ;;
esac

validate_model_api_base() {
    case "$1" in
        https://*) ;;
        http://*) test "${MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP}" = "true" || exit 64 ;;
        *) exit 64 ;;
    esac
}

case "${MEMSCOPE_MODEL_PROFILE}" in
    gateway)
        validate_model_api_base "${MEMRADER_API_BASE}"
        validate_model_api_base "${MOS_EMBEDDER_API_BASE}"
        test "${MEMRADER_API_KEY}" != "EMPTY"
        test "${MOS_EMBEDDER_API_KEY}" != "EMPTY"
        ;;
    mock)
        ;;
    *)
        exit 64
        ;;
esac

case "${EMBEDDING_DIMENSION}" in
    ''|*[!0-9]*) exit 64 ;;
esac
test "${EMBEDDING_DIMENSION}" -gt 0

mkdir -p "${MEMOS_BASE_PATH}" "${FILE_LOCAL_PATH}"
test -w "${MEMOS_BASE_PATH}"
test -w "${FILE_LOCAL_PATH}"

exec "$@"
