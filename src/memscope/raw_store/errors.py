"""Safe errors raised by Raw Store implementations."""

from memscope.errors import MemScopeError


class IdempotencyConflictError(MemScopeError):
    """A request ID was reused for a different canonical payload."""

    def __init__(self) -> None:
        super().__init__(
            code="request.conflict",
            message="Request identifier conflicts with an existing request",
            retryable=False,
        )


class RawStoreUnavailableError(MemScopeError):
    """The persistent store could not complete an operation."""

    def __init__(self) -> None:
        super().__init__(
            code="storage.unavailable",
            message="Persistent storage is currently unavailable",
            retryable=True,
        )


class RawStoreInvariantError(MemScopeError):
    """Persisted state does not satisfy the Raw Store contract."""

    def __init__(self) -> None:
        super().__init__(
            code="storage.invariant_failed",
            message="Persistent storage invariant failed",
            retryable=False,
        )


class MigrationError(MemScopeError):
    """The database schema could not be safely verified or migrated."""

    def __init__(self) -> None:
        super().__init__(
            code="storage.migration_failed",
            message="Persistent storage migration failed",
            retryable=False,
        )
