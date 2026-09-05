#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SOLUTION_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly COMPOSE_FILE="${SOLUTION_ROOT}/compose.release.yaml"
readonly DEFAULT_LOCK_FILE="${SOLUTION_ROOT}/RELEASE_LOCK.tsv"

ENV_FILE=""
IMAGE_BUNDLE=""
LOCK_FILE="${DEFAULT_LOCK_FILE}"
SHA256_FILE=""
PROJECT_NAME="memscope-organizer"
WAIT_TIMEOUT_SECONDS="300"
SKIP_LOAD="false"
COMPOSE_COMMAND=()

usage() {
    cat <<'EOF'
Load the delivered four-image bundle and start MemScope without builds or pulls.

Usage:
  ./scripts/run_release.sh --image-bundle PATH --env-file PATH [options]

Options:
  --lock-file PATH      Generated RELEASE_LOCK.tsv (default: ../RELEASE_LOCK.tsv)
  --sha256-file PATH    Verify the complete delivery set before loading images
  --project NAME        Compose project name (default: memscope-organizer)
  --wait-timeout SEC    Startup health timeout (default: 300)
  --skip-load           Reuse already loaded images after verifying their IDs
  -h, --help            Show this help

The host needs Linux x86_64, Docker Engine and Docker Compose v2. This script never
uses Python/pip/uv, builds an image, pulls an image or removes a persistent volume.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

step() {
    printf '\n==> %s\n' "$*"
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

strip_env_quotes() {
    local value="$1"
    if [[ ${#value} -ge 2 ]]; then
        if [[ "${value:0:1}" == '"' && "${value: -1}" == '"' ]]; then
            value="${value:1:${#value}-2}"
        elif [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]]; then
            value="${value:1:${#value}-2}"
        fi
    fi
    printf '%s' "${value}"
}

read_env_value() {
    local key="$1"
    local line
    line="$(grep -E "^[[:space:]]*${key}=" "${ENV_FILE}" | tail -n 1 || true)"
    [[ -n "${line}" ]] || return 1
    strip_env_quotes "${line#*=}"
}

validate_private_env() {
    [[ -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]] \
        || die "private env file is missing or is a symbolic link: ${ENV_FILE}"
    [[ -r "${ENV_FILE}" ]] || die "private env file is not readable"

    local mode key value allow_insecure
    mode="$(stat -Lc '%a' "${ENV_FILE}")"
    [[ "${mode}" =~ ^[0-7]{3,4}$ ]] || die "could not validate private env permissions"
    (( (8#${mode} & 8#077) == 0 )) \
        || die "private env file must be mode 0600 or stricter"

    local required=(
        NEO4J_PASSWORD
        MEMSCOPE_MODEL_PROFILE
        MEMRADER_MODEL
        MEMRADER_API_BASE
        MEMRADER_API_KEY
        MOS_EMBEDDER_MODEL
        MOS_EMBEDDER_API_BASE
        MOS_EMBEDDER_API_KEY
        EMBEDDING_DIMENSION
    )
    for key in "${required[@]}"; do
        value="$(read_env_value "${key}" || true)"
        [[ -n "${value}" ]] || die "required setting is missing or empty: ${key}"
        case "${value}" in
            *replace-with-*|*example.com*|*'<private-'*|*'<secret>'*|changeme|CHANGE_ME)
                die "required setting still contains a placeholder: ${key}"
                ;;
        esac
    done

    [[ "$(read_env_value MEMSCOPE_MODEL_PROFILE)" == "gateway" ]] \
        || die "MEMSCOPE_MODEL_PROFILE must be gateway"
    value="$(read_env_value NEO4J_PASSWORD)"
    (( ${#value} >= 8 )) || die "NEO4J_PASSWORD must contain at least 8 characters"
    value="$(read_env_value EMBEDDING_DIMENSION)"
    [[ "${value}" =~ ^[1-9][0-9]*$ ]] || die "EMBEDDING_DIMENSION must be a positive integer"

    allow_insecure="$(read_env_value MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP || true)"
    case "${allow_insecure:-false}" in
        true|false) ;;
        *) die "MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP must be true or false" ;;
    esac
    for key in MEMRADER_API_BASE MOS_EMBEDDER_API_BASE; do
        value="$(read_env_value "${key}")"
        if [[ "${value}" != https://* ]]; then
            [[ "${value}" == http://* ]] || die "${key} must use HTTP or HTTPS"
            [[ "${allow_insecure}" == "true" ]] \
                || die "HTTP model endpoints require MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP=true"
        fi
    done
}

verify_delivery_hashes() {
    [[ -n "${SHA256_FILE}" ]] || return 0
    [[ -f "${SHA256_FILE}" && ! -L "${SHA256_FILE}" ]] \
        || die "SHA256SUMS file is missing or unsafe: ${SHA256_FILE}"
    local sums_dir sums_name
    sums_dir="$(cd "$(dirname "${SHA256_FILE}")" && pwd)"
    sums_name="$(basename "${SHA256_FILE}")"
    step "Verifying delivered artifact hashes"
    (cd "${sums_dir}" && sha256sum --check --strict "${sums_name}") \
        || die "delivery hash verification failed"
}

expected_reference() {
    case "$1" in
        memory-api) printf '%s' 'memscope/memory-api:b10-release' ;;
        memos) printf '%s' 'memscope/memos:2.0.32-b10-release' ;;
        neo4j) printf '%s' 'neo4j:5.26.6-community' ;;
        qdrant) printf '%s' 'qdrant/qdrant:v1.15.3' ;;
        *) return 1 ;;
    esac
}

verify_image_lock() {
    [[ -f "${LOCK_FILE}" && ! -L "${LOCK_FILE}" ]] \
        || die "release image lock is missing or unsafe: ${LOCK_FILE}"

    local role reference expected_id revision extra expected_ref actual_id actual_platform actual_revision count=0
    declare -A seen=()
    while IFS=$'\t' read -r role reference expected_id revision extra; do
        [[ -n "${role}" && "${role:0:1}" != "#" ]] || continue
        [[ -z "${extra:-}" ]] || die "release image lock contains extra fields"
        expected_ref="$(expected_reference "${role}" || true)"
        [[ -n "${expected_ref}" && "${reference}" == "${expected_ref}" ]] \
            || die "release image lock contains an unexpected role or reference"
        [[ -z "${seen[${role}]:-}" ]] || die "release image lock contains duplicate roles"
        [[ "${expected_id}" =~ ^sha256:[0-9a-f]{64}$ ]] \
            || die "release image lock contains an invalid image ID"
        seen["${role}"]=1
        actual_id="$(docker image inspect --format '{{.Id}}' "${reference}" 2>/dev/null || true)"
        [[ "${actual_id}" == "${expected_id}" ]] \
            || die "loaded image ID does not match RELEASE_LOCK.tsv for ${role}"
        actual_platform="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' \
            "${reference}" 2>/dev/null || true)"
        [[ "${actual_platform}" == "linux/amd64" ]] \
            || die "loaded image platform is not linux/amd64 for ${role}"
        if [[ "${revision}" != "-" ]]; then
            [[ "${revision}" =~ ^[0-9a-f]{40}$ ]] \
                || die "release image lock contains an invalid source revision"
            actual_revision="$(docker image inspect \
                --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' \
                "${reference}" 2>/dev/null || true)"
            [[ "${actual_revision}" == "${revision}" ]] \
                || die "image source revision label does not match for ${role}"
        fi
        ((count += 1))
    done < "${LOCK_FILE}"
    (( count == 4 )) || die "release image lock must contain exactly four images"
    for role in memory-api memos neo4j qdrant; do
        [[ -n "${seen[${role}]:-}" ]] || die "release image lock is missing role: ${role}"
    done
}

compose() {
    "${COMPOSE_COMMAND[@]}" \
        --project-directory "${SOLUTION_ROOT}" \
        --file "${COMPOSE_FILE}" \
        --env-file "${ENV_FILE}" \
        --project-name "${PROJECT_NAME}" \
        "$@"
}

while (( $# > 0 )); do
    case "$1" in
        --image-bundle) (( $# >= 2 )) || die "--image-bundle requires a path"; IMAGE_BUNDLE="$2"; shift 2 ;;
        --env-file) (( $# >= 2 )) || die "--env-file requires a path"; ENV_FILE="$2"; shift 2 ;;
        --lock-file) (( $# >= 2 )) || die "--lock-file requires a path"; LOCK_FILE="$2"; shift 2 ;;
        --sha256-file) (( $# >= 2 )) || die "--sha256-file requires a path"; SHA256_FILE="$2"; shift 2 ;;
        --project) (( $# >= 2 )) || die "--project requires a name"; PROJECT_NAME="$2"; shift 2 ;;
        --wait-timeout) (( $# >= 2 )) || die "--wait-timeout requires seconds"; WAIT_TIMEOUT_SECONDS="$2"; shift 2 ;;
        --skip-load) SKIP_LOAD="true"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

[[ "$(uname -s)" == "Linux" ]] || die "organizer release supports Linux only"
[[ "$(uname -m)" == "x86_64" ]] || die "organizer release is built for Linux x86_64"
[[ -n "${ENV_FILE}" ]] || die "--env-file is required"
[[ -n "${IMAGE_BUNDLE}" || "${SKIP_LOAD}" == "true" ]] \
    || die "--image-bundle is required unless --skip-load is used"
[[ "${PROJECT_NAME}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid Compose project name"
[[ "${WAIT_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] || die "--wait-timeout must be positive"

require_command docker
require_command grep
require_command sha256sum
require_command stat
docker info >/dev/null 2>&1 || die "Docker daemon is unavailable or permission was denied"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required"
compose_version="$(docker compose version --short 2>/dev/null || true)"
[[ "${compose_version}" =~ ^v?([0-9]+)\. ]] || die "could not determine Docker Compose version"
(( BASH_REMATCH[1] >= 2 )) || die "Docker Compose v2 or newer is required"
COMPOSE_COMMAND=(docker compose)

if [[ -r /proc/meminfo ]]; then
    total_memory_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
    if [[ "${total_memory_kib}" =~ ^[0-9]+$ ]] && (( total_memory_kib < 10 * 1024 * 1024 )); then
        printf 'WARNING: less than 10 GiB RAM detected; default service ceilings total 8.5 GiB.\n' >&2
    fi
fi

validate_private_env
verify_delivery_hashes

if [[ "${SKIP_LOAD}" != "true" ]]; then
    [[ -f "${IMAGE_BUNDLE}" && ! -L "${IMAGE_BUNDLE}" ]] \
        || die "image bundle is missing or unsafe: ${IMAGE_BUNDLE}"
    step "Loading the four-image offline bundle"
    docker load --input "${IMAGE_BUNDLE}"
fi

step "Verifying all four loaded image IDs and source labels"
verify_image_lock

step "Validating release configuration without rendering secrets"
compose config --quiet

step "Starting four services without build or pull"
compose up --detach --no-build --pull never --wait --wait-timeout "${WAIT_TIMEOUT_SECONDS}"
compose ps

published_port="$(compose port memory-api 8080 | head -n 1)"
[[ -n "${published_port}" ]] || die "memory-api has no published host port"
printf '\nMemScope release started. Public endpoint: http://127.0.0.1:%s\n' "${published_port##*:}"
printf 'Next: ./scripts/verify_release.sh --env-file <private-env> --project %s\n' "${PROJECT_NAME}"
