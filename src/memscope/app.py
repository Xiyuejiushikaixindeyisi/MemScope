"""Dependency-injectable FastAPI application factory."""

import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI

from memscope import __version__
from memscope.api.errors import install_error_handlers, install_request_logging
from memscope.api.routes import create_contest_router
from memscope.logging_config import LOGGER_NAME, configure_logging
from memscope.operations import (
    AddCommand,
    ContestOperations,
    MemoryEvidence,
    SearchQuery,
    UnavailableContestOperations,
)
from memscope.runtime import RuntimeResources, open_runtime
from memscope.settings import AppProfile, AppSettings, load_settings


class _StateOperations:
    """Route dependency that follows lifespan-installed application operations."""

    def __init__(self, application: FastAPI) -> None:
        self._application = application

    @property
    def _operations(self) -> ContestOperations:
        return self._application.state.operations  # type: ignore[no-any-return]

    async def is_ready(self) -> bool:
        return await self._operations.is_ready()

    async def add(self, command: AddCommand) -> None:
        await self._operations.add(command)

    async def search(self, query: SearchQuery) -> Sequence[MemoryEvidence]:
        return await self._operations.search(query)


def create_app(
    settings: AppSettings | None = None,
    *,
    operations: ContestOperations | None = None,
) -> FastAPI:
    """Create an isolated ASGI application from validated settings."""

    effective_settings = settings if settings is not None else load_settings()
    configure_logging(effective_settings)

    resources: RuntimeResources | None = None

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        nonlocal resources
        if operations is None and effective_settings.app_profile is AppProfile.MEMOS_ADD:
            resources = await open_runtime(effective_settings)
            application.state.operations = resources.operations
        try:
            yield
        finally:
            application.state.operations = UnavailableContestOperations()
            if resources is not None:
                await resources.close()
                resources = None

    application = FastAPI(
        title="MemScope",
        description="Contest HTTP adapter for the MemScope memory service.",
        version=__version__,
        lifespan=lifespan,
    )
    effective_operations = operations if operations is not None else UnavailableContestOperations()
    application.state.settings = effective_settings
    application.state.operations = effective_operations
    install_error_handlers(application)
    install_request_logging(application)
    application.include_router(
        create_contest_router(
            settings=effective_settings,
            operations=_StateOperations(application),
        )
    )
    logging.getLogger(LOGGER_NAME).info("application_initialized")
    return application
