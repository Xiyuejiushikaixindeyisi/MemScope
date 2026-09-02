"""FastAPI application factory without contest business routes."""

import logging

from fastapi import FastAPI

from memscope import __version__
from memscope.logging_config import LOGGER_NAME, configure_logging
from memscope.settings import AppSettings, load_settings


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create an isolated ASGI application from validated settings."""

    effective_settings = settings if settings is not None else load_settings()
    configure_logging(effective_settings)

    application = FastAPI(
        title="MemScope",
        description="B00 engineering foundation; contest endpoints are delivered in B01.",
        version=__version__,
    )
    application.state.settings = effective_settings
    logging.getLogger(LOGGER_NAME).info("application_initialized")
    return application
