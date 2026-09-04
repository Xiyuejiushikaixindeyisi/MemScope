#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly DEFAULT_ENV_FILE="${MEMSCOPE_CONFIG_DIR:-${REPO_ROOT}}/compose.env"
readonly DEFAULT_PROJECT_NAME="memscope"
readonly REQUIRED_UV_VERSION="0.12.9"

ENV_FILE="${DEFAULT_ENV_FILE}"
PROJECT_NAME="${DEFAULT_PROJECT_NAME}"
MODE="deploy"
WAIT_TIMEOUT_SECONDS="300"
COMPOSE_COMMAND=()

usage() {
    cat <<'EOF'
Build and deploy MemScope on a Linux Docker host.

Usage:
  ./scripts/deploy_linux.sh [options]

Options:
  --env-file PATH       Private Compose environment file
                        (default: <repository>/compose.env)
  --project NAME        Compose project name (default: memscope)
  --wait-timeout SEC    Startup health timeout (default: 300)
  --check-only          Validate prerequisites and configuration only
  --build-only          Synchronize and build images without starting services
  -h, --help            Show this help

The default mode performs:
  uv sync --frozen
  third-party source verification
  docker compose config validation
  image build
  detached startup with health waiting
  public health verification

The script never creates credentials and never removes persistent volumes.
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

initialize_private_env() {
    [[ ! -e "${ENV_FILE}" ]] || return 0

    local template="${REPO_ROOT}/deploy/compose.env.example"
    local destination_dir editor_spec
    local -a editor_command
    [[ -f "${template}" ]] || die "configuration template not found: ${template}"

    destination_dir="$(dirname "${ENV_FILE}")"
    if [[ ! -d "${destination_dir}" ]]; then
        mkdir -p -- "${destination_dir}" \
            || die "cannot create configuration directory: ${destination_dir}"
        chmod 0750 "${destination_dir}"
    fi

    step "Creating the private configuration"
    install -m 0600 "${template}" "${ENV_FILE}" \
        || die "cannot create ${ENV_FILE}; choose a writable path or create the directory with the required ownership"
    printf 'Created %s with mode 0600.\n' "${ENV_FILE}"

    editor_spec="${VISUAL:-${EDITOR:-}}"
    if [[ -z "${editor_spec}" ]]; then
        if [[ ! -t 0 || ! -t 1 ]]; then
            die "configuration was created but no editor is configured; set EDITOR and rerun"
        fi
        for candidate in sensible-editor editor vi nano; do
            if command -v "${candidate}" >/dev/null 2>&1; then
                editor_spec="${candidate}"
                break
            fi
        done
    fi
    [[ -n "${editor_spec}" ]] || die "configuration was created but no editor was found; set EDITOR and rerun"

    read -r -a editor_command <<< "${editor_spec}"
    command -v "${editor_command[0]}" >/dev/null 2>&1 \
        || die "configured editor was not found: ${editor_command[0]}"
    "${editor_command[@]}" "${ENV_FILE}" \
        || die "editor exited unsuccessfully; configuration remains at ${ENV_FILE}"
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

validate_secret_file() {
    [[ -f "${ENV_FILE}" ]] || die "private env file not found: ${ENV_FILE}; copy deploy/compose.env.example outside source control and replace every placeholder"
    [[ -r "${ENV_FILE}" ]] || die "private env file is not readable: ${ENV_FILE}"

    local mode
    mode="$(stat -Lc '%a' "${ENV_FILE}")"
    (( (8#${mode} & 8#077) == 0 )) || die "private env file must not be accessible by group/others (expected mode 0600 or stricter): ${ENV_FILE}"

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
    local allow_insecure_http key value
    for key in "${required[@]}"; do
        value="$(read_env_value "${key}" || true)"
        [[ -n "${value}" ]] || die "required setting is missing or empty: ${key}"
        case "${value}" in
            *replace-with-*|*example.com*|*'<private-'*|*'<secret>'*|changeme|CHANGE_ME)
                die "required setting still contains a placeholder: ${key}"
                ;;
        esac
    done

    value="$(read_env_value MEMSCOPE_MODEL_PROFILE)"
    [[ "${value}" == "gateway" ]] || die "MEMSCOPE_MODEL_PROFILE must be gateway for this deployment script"

    allow_insecure_http="$(read_env_value MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP || true)"
    case "${allow_insecure_http:-false}" in
        true|false) ;;
        *) die "MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP must be true or false" ;;
    esac

    value="$(read_env_value MEMRADER_API_BASE)"
    if [[ "${value}" != https://* ]]; then
        [[ "${value}" == http://* ]] || die "MEMRADER_API_BASE must use HTTP or HTTPS"
        [[ "${allow_insecure_http}" == "true" ]] || die "HTTP model endpoints require MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP=true"
    fi
    value="$(read_env_value MOS_EMBEDDER_API_BASE)"
    if [[ "${value}" != https://* ]]; then
        [[ "${value}" == http://* ]] || die "MOS_EMBEDDER_API_BASE must use HTTP or HTTPS"
        [[ "${allow_insecure_http}" == "true" ]] || die "HTTP model endpoints require MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP=true"
    fi

    value="$(read_env_value EMBEDDING_DIMENSION)"
    [[ "${value}" =~ ^[1-9][0-9]*$ ]] || die "EMBEDDING_DIMENSION must be a positive integer"

    value="$(read_env_value NEO4J_PASSWORD)"
    (( ${#value} >= 8 )) || die "NEO4J_PASSWORD must contain at least 8 characters"
}

compose() {
    "${COMPOSE_COMMAND[@]}" \
        --project-directory "${REPO_ROOT}" \
        --file "${REPO_ROOT}/compose.yaml" \
        --env-file "${ENV_FILE}" \
        --project-name "${PROJECT_NAME}" \
        "$@"
}

verify_public_health() {
    local mapping port
    mapping="$(compose port memory-api 8080 | head -n 1)"
    [[ -n "${mapping}" ]] || die "could not resolve the published memory-api port"
    port="${mapping##*:}"
    [[ "${port}" =~ ^[0-9]+$ ]] || die "unexpected memory-api port mapping"

    uv run python - "${port}" <<'PY'
import json
import sys
import urllib.request

port = int(sys.argv[1])
with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=10) as response:
    body = json.load(response)
if response.status != 200 or body != {"status": "ok"}:
    raise SystemExit("public health response did not match the required contract")
PY
    printf 'Public endpoint: http://127.0.0.1:%s\n' "${port}"
}

while (( $# > 0 )); do
    case "$1" in
        --env-file)
            (( $# >= 2 )) || die "--env-file requires a path"
            ENV_FILE="$2"
            shift 2
            ;;
        --project)
            (( $# >= 2 )) || die "--project requires a name"
            PROJECT_NAME="$2"
            shift 2
            ;;
        --wait-timeout)
            (( $# >= 2 )) || die "--wait-timeout requires seconds"
            WAIT_TIMEOUT_SECONDS="$2"
            shift 2
            ;;
        --check-only)
            MODE="check"
            shift
            ;;
        --build-only)
            MODE="build"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown argument: $1"
            ;;
    esac
done

[[ "$(uname -s)" == "Linux" ]] || die "this script supports Linux only"
[[ "$(uname -m)" == "x86_64" ]] || die "this deployment is pinned for Linux x86_64"
[[ "${PROJECT_NAME}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid Compose project name: ${PROJECT_NAME}"
[[ "${WAIT_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] || die "--wait-timeout must be a positive integer"

require_command uv
require_command docker
require_command install
require_command realpath
require_command sha256sum
require_command stat

actual_uv_version="$(uv --version | awk '{print $2}')"
[[ "${actual_uv_version}" == "${REQUIRED_UV_VERSION}" ]] || die "uv ${REQUIRED_UV_VERSION} is required; found ${actual_uv_version:-unknown}"
docker info >/dev/null 2>&1 || die "Docker daemon is unavailable or the current user lacks permission"
if docker compose version >/dev/null 2>&1; then
    COMPOSE_COMMAND=(docker compose)
elif command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then
    COMPOSE_COMMAND=(docker-compose)
else
    die "Docker Compose is required; neither 'docker compose' nor 'docker-compose' is available"
fi
compose_version="$("${COMPOSE_COMMAND[@]}" version --short 2>/dev/null || true)"
if [[ ! "${compose_version}" =~ ^v?([0-9]+)\. ]]; then
    die "could not determine the Docker Compose version"
fi
(( BASH_REMATCH[1] >= 2 )) || die "Docker Compose v2 or newer is required; found ${compose_version}"

if [[ -r /proc/meminfo ]]; then
    total_memory_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
    if [[ "${total_memory_kib}" =~ ^[0-9]+$ ]] && (( total_memory_kib < 8 * 1024 * 1024 )); then
        printf 'WARNING: less than 8 GiB RAM detected; the default service ceilings may not fit.\n' >&2
    fi
fi

ENV_FILE="$(realpath -m "${ENV_FILE}")"
initialize_private_env

step "Validating private configuration"
validate_secret_file

step "Verifying the locked MemOS source archive"
(
    cd "${REPO_ROOT}/third_party/memos"
    sha256sum --check SHA256SUMS
)

step "Validating Compose interpolation"
compose config --quiet

if [[ "${MODE}" == "check" ]]; then
    printf '\nPreflight checks passed. No environment was synchronized and no service was changed.\n'
    exit 0
fi

step "Synchronizing the locked MemScope environment"
(
    cd "${REPO_ROOT}"
    uv sync --frozen
)

step "Building the memory-api and MemOS images"
compose build memory-api memos

if [[ "${MODE}" == "build" ]]; then
    printf '\nBuild completed. No service was started.\n'
    exit 0
fi

step "Starting Neo4j, Qdrant, MemOS, and memory-api"
compose up --detach --pull missing --wait --wait-timeout "${WAIT_TIMEOUT_SECONDS}"

step "Verifying the public health contract"
verify_public_health

step "Deployment status"
compose ps
printf '\nMemScope deployment completed successfully. Persistent volumes were preserved.\n'
