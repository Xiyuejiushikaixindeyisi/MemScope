"""Tests for structured, idempotent and conservative logging."""

import json
import logging
from typing import Any

import pytest

from memscope.logging_config import LOGGER_NAME, configure_logging
from memscope.settings import AppSettings
from tests.support import make_settings


def _json_settings(**overrides: Any) -> AppSettings:
    return make_settings(log_format="json", **overrides)


def test_json_logging_has_required_fields_and_rejects_arbitrary_extras(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(_json_settings())
    logger = logging.getLogger(LOGGER_NAME)

    logger.error(
        "operation_failed",
        extra={
            "error_code": "operation.failed",
            "retryable": False,
            "api_key": "must-not-appear",
        },
    )

    payload = json.loads(capsys.readouterr().err)
    assert payload["level"] == "ERROR"
    assert payload["logger"] == LOGGER_NAME
    assert payload["event"] == "operation_failed"
    assert payload["error_code"] == "operation.failed"
    assert payload["retryable"] is False
    assert payload["timestamp"].endswith("Z")
    assert "api_key" not in payload
    assert "must-not-appear" not in payload.values()


def test_logging_configuration_is_idempotent(capsys: pytest.CaptureFixture[str]) -> None:
    settings = _json_settings()
    configure_logging(settings)
    configure_logging(settings)
    logger = logging.getLogger(LOGGER_NAME)

    logger.info("one_event")

    lines = capsys.readouterr().err.splitlines()
    assert len(logger.handlers) == 1
    assert len(lines) == 1


def test_log_level_filters_lower_priority_records(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(_json_settings(log_level="WARNING"))
    logger = logging.getLogger(LOGGER_NAME)

    logger.info("hidden")
    logger.warning("visible")

    assert "hidden" not in capsys.readouterr().err


def test_console_logging_is_compact(capsys: pytest.CaptureFixture[str]) -> None:
    settings = make_settings(log_format="console")
    configure_logging(settings)

    logging.getLogger(LOGGER_NAME).info("ready")

    assert capsys.readouterr().err == "INFO memscope ready\n"


def test_json_logging_records_exception_type_without_exception_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(_json_settings())
    logger = logging.getLogger(LOGGER_NAME)

    try:
        raise ValueError("must-not-be-logged")
    except ValueError:
        logger.exception("safe_failure")

    payload = json.loads(capsys.readouterr().err)
    assert payload["exception_type"] == "ValueError"
    assert "must-not-be-logged" not in payload.values()


def test_http_logging_allows_only_bounded_metadata(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(_json_settings())
    logger = logging.getLogger(LOGGER_NAME)

    logger.info(
        "http_request_completed",
        extra={
            "http_method": "POST",
            "http_path": "/add",
            "status_code": 200,
            "total_duration_ms": 1.25,
            "request_id": "must-not-appear",
            "content": "private-message",
        },
    )

    payload = json.loads(capsys.readouterr().err)
    assert payload["http_method"] == "POST"
    assert payload["http_path"] == "/add"
    assert payload["status_code"] == 200
    assert payload["total_duration_ms"] == 1.25
    assert "request_id" not in payload
    assert "content" not in payload
    assert "must-not-appear" not in payload.values()
    assert "private-message" not in payload.values()


def test_raw_store_logging_allows_only_bounded_metadata(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(_json_settings())
    logger = logging.getLogger(LOGGER_NAME)

    logger.info(
        "raw_store_operation_completed",
        extra={
            "storage_operation": "prepare_add",
            "storage_result": "new",
            "schema_version": 1,
            "raw_store_duration_ms": 2.5,
            "database_path": "/private/database.db",
            "payload_sha256": "must-not-appear",
            "request_id": "also-private",
        },
    )

    payload = json.loads(capsys.readouterr().err)
    assert payload["storage_operation"] == "prepare_add"
    assert payload["storage_result"] == "new"
    assert payload["schema_version"] == 1
    assert payload["raw_store_duration_ms"] == 2.5
    assert "database_path" not in payload
    assert "payload_sha256" not in payload
    assert "request_id" not in payload
    assert "must-not-appear" not in payload.values()
