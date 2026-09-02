"""Tests for optional contest shared-key authentication."""

import pytest
from starlette.datastructures import Headers

from memscope.api.auth import AuthenticationError, authenticate
from memscope.settings import AppSettings
from tests.support import make_settings


def _shared_key_settings() -> AppSettings:
    return make_settings(contest_auth_mode="shared_key", contest_api_key="correct-key")


@pytest.mark.parametrize(
    "headers",
    [
        Headers({"Authorization": "Bearer correct-key"}),
        Headers({"Authorization": "bearer correct-key"}),
        Headers({"Authorization": "Token correct-key"}),
        Headers({"X-Api-Key": "correct-key"}),
    ],
)
def test_authenticate_accepts_each_supported_single_carrier(headers: Headers) -> None:
    authenticate(headers, _shared_key_settings())


def test_authenticate_none_mode_ignores_headers() -> None:
    authenticate(Headers({"Authorization": "Malformed"}), make_settings())


@pytest.mark.parametrize(
    "headers",
    [
        Headers(),
        Headers({"Authorization": "Bearer wrong"}),
        Headers({"Authorization": "Basic correct-key"}),
        Headers({"Authorization": "Bearer"}),
        Headers({"X-Api-Key": ""}),
        Headers(
            raw=[
                (b"authorization", b"Bearer correct-key"),
                (b"x-api-key", b"correct-key"),
            ]
        ),
        Headers(
            raw=[
                (b"authorization", b"Bearer correct-key"),
                (b"authorization", b"Token correct-key"),
            ]
        ),
    ],
)
def test_authenticate_rejects_missing_malformed_wrong_or_ambiguous_credentials(
    headers: Headers,
) -> None:
    with pytest.raises(AuthenticationError) as captured:
        authenticate(headers, _shared_key_settings())

    assert "correct-key" not in str(captured.value)
