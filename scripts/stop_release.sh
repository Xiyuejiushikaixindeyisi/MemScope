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

ENV_FILE=""
PROJECT_NAME="memscope-organizer"

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

while (( $# > 0 )); do
    case "$1" in
        --env-file) (( $# >= 2 )) || die "--env-file requires a path"; ENV_FILE="$2"; shift 2 ;;
        --project) (( $# >= 2 )) || die "--project requires a name"; PROJECT_NAME="$2"; shift 2 ;;
        -h|--help)
            printf 'Usage: ./scripts/stop_release.sh --env-file PATH [--project NAME]\n'
            printf 'Stops/removes release containers and network while preserving every named volume.\n'
            exit 0
            ;;
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

"${MEMSCOPE_COMPOSE_COMMAND[@]}" \
    --project-directory "${SOLUTION_ROOT}" \
    --file "${COMPOSE_FILE}" \
    --env-file "${ENV_FILE}" \
    --project-name "${PROJECT_NAME}" \
    config --quiet
"${MEMSCOPE_COMPOSE_COMMAND[@]}" \
    --project-directory "${SOLUTION_ROOT}" \
    --file "${COMPOSE_FILE}" \
    --env-file "${ENV_FILE}" \
    --project-name "${PROJECT_NAME}" \
    down --remove-orphans --timeout 30

printf 'Release containers stopped; named volumes were preserved.\n'
