"""Dependency-injectable FastAPI application factory."""

import logging

from fastapi import FastAPI

from memscope import __version__
from memscope.api.errors import install_error_handlers, install_request_logging
from memscope.api.routes import create_contest_router
from memscope.logging_config import LOGGER_NAME, configure_logging
from memscope.operations import ContestOperations, UnavailableContestOperations
from memscope.settings import AppSettings, load_settings


def create_app(
    settings: AppSettings | None = None,
    *,
    operations: ContestOperations | None = None,
) -> FastAPI:
    """Create an isolated ASGI application from validated settings."""

    effective_settings = settings if settings is not None else load_settings()
    configure_logging(effective_settings)

    application = FastAPI(
        title="MemScope",
        description="Contest HTTP adapter for the MemScope memory service.",
        version=__version__,
    )
    effective_operations = operations if operations is not None else UnavailableContestOperations()
    application.state.settings = effective_settings
    application.state.operations = effective_operations
    install_error_handlers(application)
    install_request_logging(application)
    application.include_router(
        create_contest_router(settings=effective_settings, operations=effective_operations)
    )
    logging.getLogger(LOGGER_NAME).info("application_initialized")
    return application
