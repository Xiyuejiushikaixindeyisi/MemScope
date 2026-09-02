"""Optional shared-key authentication for contest operations."""

import secrets

from starlette.datastructures import Headers

from memscope.errors import MemScopeError
from memscope.settings import AppSettings, ContestAuthMode


class AuthenticationError(MemScopeError):
    """Deliberately non-specific credential rejection."""

    def __init__(self) -> None:
        super().__init__(
            code="auth.invalid",
            message="Authentication failed",
            retryable=False,
        )


def authenticate(headers: Headers, settings: AppSettings) -> None:
    """Authenticate exactly one supported credential carrier when enabled."""

    if settings.contest_auth_mode is ContestAuthMode.NONE:
        return

    credentials: list[str] = []
    malformed = False

    for value in headers.getlist("authorization"):
        parts = value.strip().split()
        if len(parts) != 2 or parts[0].lower() not in {"bearer", "token"} or not parts[1]:
            malformed = True
            continue
        credentials.append(parts[1])

    for value in headers.getlist("x-api-key"):
        credential = value.strip()
        if not credential:
            malformed = True
            continue
        credentials.append(credential)

    configured = settings.contest_api_key
    if malformed or len(credentials) != 1 or configured is None:
        raise AuthenticationError()
    if not secrets.compare_digest(credentials[0], configured.get_secret_value()):
        raise AuthenticationError()
