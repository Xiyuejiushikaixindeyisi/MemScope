"""Tests for transport-independent error contracts."""

import pytest

from memscope.errors import ConfigurationError, MemScopeError


def test_memscope_error_exposes_stable_safe_fields() -> None:
    error = MemScopeError(code="dependency.timeout", message="Dependency timed out", retryable=True)

    assert error.code == "dependency.timeout"
    assert error.message == "Dependency timed out"
    assert error.retryable is True
    assert str(error) == "dependency.timeout: Dependency timed out"


@pytest.mark.parametrize(("code", "message"), [("", "message"), ("code", "  ")])
def test_memscope_error_rejects_empty_identity(code: str, message: str) -> None:
    with pytest.raises(ValueError):
        MemScopeError(code=code, message=message)


def test_configuration_error_normalizes_fields_without_values() -> None:
    error = ConfigurationError([" port ", "host", "port", ""])

    assert error.fields == ("host", "port")
    assert error.code == "configuration.invalid"
    assert error.retryable is False
    assert "host, port" in str(error)


def test_configuration_error_uses_safe_unknown_field() -> None:
    error = ConfigurationError([])

    assert error.fields == ("unknown",)
