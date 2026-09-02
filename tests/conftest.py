"""Shared test isolation for process-global logging state."""

import logging
from collections.abc import Iterator

import pytest

from memscope.logging_config import LOGGER_NAME


@pytest.fixture(autouse=True)
def restore_memscope_logger() -> Iterator[None]:
    """Restore the package logger after every test."""

    logger = logging.getLogger(LOGGER_NAME)
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate
    yield
    for handler in tuple(logger.handlers):
        if handler not in original_handlers:
            logger.removeHandler(handler)
            handler.close()
    logger.handlers[:] = original_handlers
    logger.setLevel(original_level)
    logger.propagate = original_propagate
