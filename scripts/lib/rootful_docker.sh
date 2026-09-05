#!/usr/bin/env bash

# Shared host-boundary and rootful-Docker selection for MemScope operator scripts.
# The caller must provide die(). Scripts stay unprivileged; only Docker commands
# may be elevated so that host files remain owned by the invoking user.

MEMSCOPE_DOCKER_COMMAND=()
MEMSCOPE_COMPOSE_COMMAND=()

memscope_assert_unprivileged_operator() {
    (( EUID != 0 )) \
        || die "run this script as the ordinary operator, not with sudo; only Docker commands are elevated"
    [[ -n "${HOME:-}" && -d "${HOME}" ]] || die "the operator HOME directory is unavailable"

    local resolved_home
    resolved_home="$(realpath -e -- "${HOME}")" \
        || die "could not resolve the operator HOME directory"
    [[ "${resolved_home}" != "/" ]] || die "the operator HOME directory must not be /"
}

memscope_require_home_path() {
    local path="$1"
    local label="$2"
    local resolved_home resolved_path

    resolved_home="$(realpath -e -- "${HOME}")" \
        || die "could not resolve the operator HOME directory"
    resolved_path="$(realpath -m -- "${path}")" \
        || die "could not resolve ${label}: ${path}"
    case "${resolved_path}" in
        "${resolved_home}"|"${resolved_home}"/*) ;;
        *) die "${label} must stay under the ordinary operator HOME (${resolved_home}): ${resolved_path}" ;;
    esac
}

_memscope_is_rootful_docker() {
    local security_options
    security_options="$("$@" info --format '{{json .SecurityOptions}}' 2>/dev/null)" || return 1
    [[ -n "${security_options}" && "${security_options,,}" != *rootless* ]]
}

memscope_initialize_rootful_docker() {
    command -v docker >/dev/null 2>&1 || die "required command not found: docker"

    local docker_path sudo_path env_path
    docker_path="$(command -v docker)"
    if _memscope_is_rootful_docker "${docker_path}"; then
        MEMSCOPE_DOCKER_COMMAND=("${docker_path}")
    else
        sudo_path="$(command -v sudo || true)"
        env_path="$(command -v env || true)"
        if [[ -n "${sudo_path}" && -n "${env_path}" ]] \
            && _memscope_is_rootful_docker \
                "${env_path}" -u DOCKER_HOST -u DOCKER_CONTEXT \
                "${sudo_path}" -n -- "${docker_path}"; then
            MEMSCOPE_DOCKER_COMMAND=(
                "${env_path}" -u DOCKER_HOST -u DOCKER_CONTEXT
                "${sudo_path}" -n -- "${docker_path}"
            )
        else
            die "a rootful Docker daemon is required; run 'sudo -v', ensure the system Docker service is active, and retry as the ordinary user"
        fi
    fi

    "${MEMSCOPE_DOCKER_COMMAND[@]}" compose version >/dev/null 2>&1 \
        || die "Docker Compose v2 is required on the selected rootful Docker installation"
    local compose_version
    compose_version="$("${MEMSCOPE_DOCKER_COMMAND[@]}" compose version --short 2>/dev/null || true)"
    [[ "${compose_version}" =~ ^v?([0-9]+)\. ]] \
        || die "could not determine Docker Compose version"
    (( BASH_REMATCH[1] >= 2 )) \
        || die "Docker Compose v2 or newer is required; found ${compose_version}"
    MEMSCOPE_COMPOSE_COMMAND=("${MEMSCOPE_DOCKER_COMMAND[@]}" compose)
}
