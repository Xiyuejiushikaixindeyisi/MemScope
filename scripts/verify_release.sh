#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SOLUTION_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly COMPOSE_FILE="${SOLUTION_ROOT}/compose.release.yaml"
readonly ROOTFUL_DOCKER_LIB="${SCRIPT_DIR}/lib/rootful_docker.sh"
[[ -r "${ROOTFUL_DOCKER_LIB}" ]] || {
    printf 'ERROR: rootful Docker helper is missing: %s\n' "${ROOTFUL_DOCKER_LIB}" >&2
    exit 1
}
# shellcheck source=scripts/lib/rootful_docker.sh
source "${ROOTFUL_DOCKER_LIB}"
PUBLIC_VERIFIER="${SOLUTION_ROOT}/code/scripts/verify_b06_candidate.py"
if [[ ! -f "${PUBLIC_VERIFIER}" ]]; then
    PUBLIC_VERIFIER="${SCRIPT_DIR}/verify_b06_candidate.py"
fi

ENV_FILE=""
PROJECT_NAME="memscope-organizer"

usage() {
    cat <<'EOF'
Verify an already-started organizer release without host Python dependencies.

Usage:
  ./scripts/verify_release.sh --env-file PATH [--project NAME]

The script checks four healthy containers, Neo4j and Qdrant readiness, then runs
the sanitized Add/replay/Search/cross-user smoke from inside the memory-api image.
It writes no request body, memory content, vector, credential or provider response.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

step() {
    printf '\n==> %s\n' "$*"
}

compose() {
    "${MEMSCOPE_COMPOSE_COMMAND[@]}" \
        --project-directory "${SOLUTION_ROOT}" \
        --file "${COMPOSE_FILE}" \
        --env-file "${ENV_FILE}" \
        --project-name "${PROJECT_NAME}" \
        "$@"
}

while (( $# > 0 )); do
    case "$1" in
        --env-file) (( $# >= 2 )) || die "--env-file requires a path"; ENV_FILE="$2"; shift 2 ;;
        --project) (( $# >= 2 )) || die "--project requires a name"; PROJECT_NAME="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

[[ -n "${ENV_FILE}" && -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]] \
    || die "a regular private --env-file is required"
[[ "${PROJECT_NAME}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid Compose project name"
command -v realpath >/dev/null 2>&1 || die "required command not found: realpath"
memscope_assert_unprivileged_operator
memscope_require_home_path "${SOLUTION_ROOT}" "solution directory"
memscope_require_home_path "${ENV_FILE}" "private env file"
memscope_initialize_rootful_docker
[[ -f "${PUBLIC_VERIFIER}" && ! -L "${PUBLIC_VERIFIER}" ]] \
    || die "public verifier is missing from solution/code"

compose config --quiet

step "Checking all four container health states"
for service in memory-api memos neo4j qdrant; do
    container_id="$(compose ps --quiet "${service}")"
    [[ -n "${container_id}" ]] || die "service container is missing: ${service}"
    running="$("${MEMSCOPE_DOCKER_COMMAND[@]}" inspect --format '{{.State.Running}}' "${container_id}")"
    health="$("${MEMSCOPE_DOCKER_COMMAND[@]}" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "${container_id}")"
    [[ "${running}" == "true" && "${health}" == "healthy" ]] \
        || die "service is not running and healthy: ${service}"
    printf '%s: healthy\n' "${service}"
done

step "Checking Neo4j query and Qdrant HTTP readiness"
compose exec -T neo4j sh -c \
    'cypher-shell -u neo4j -p "${NEO4J_AUTH#neo4j/}" "RETURN 1 AS ready;" >/dev/null 2>&1'
compose exec -T memos python -c \
    "import urllib.request; r=urllib.request.urlopen('http://qdrant:6333/readyz',timeout=3); assert r.status==200"

step "Running sanitized real Add/Search smoke inside memory-api"
compose exec -T memory-api python - --base-url http://127.0.0.1:8080 --require-hit \
    < "${PUBLIC_VERIFIER}"

mapping="$(compose port memory-api 8080 | head -n 1)"
[[ -n "${mapping}" ]] || die "memory-api public port is not published"
printf '\nRelease verification passed. Evaluation origin: http://127.0.0.1:%s\n' "${mapping##*:}"
