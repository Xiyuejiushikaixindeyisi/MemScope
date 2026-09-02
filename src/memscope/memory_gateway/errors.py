"""Transport-independent and sanitized Memory Gateway errors."""

from memscope.errors import MemScopeError


class GatewayRateLimitedError(MemScopeError):
    """The upstream memory path rejected work due to rate limiting."""

    def __init__(self) -> None:
        super().__init__(
            code="gateway.rate_limited",
            message="Memory gateway is rate limited",
            retryable=True,
        )


class GatewayUnavailableError(MemScopeError):
    """The memory path is closed, disconnected or temporarily unavailable."""

    def __init__(self) -> None:
        super().__init__(
            code="gateway.unavailable",
            message="Memory gateway is currently unavailable",
            retryable=True,
        )


class GatewayTimeoutError(MemScopeError):
    """The upstream memory operation exceeded its caller-defined timeout."""

    def __init__(self) -> None:
        super().__init__(
            code="gateway.timeout",
            message="Memory gateway operation timed out",
            retryable=True,
        )


class GatewayProtocolError(MemScopeError):
    """The memory provider returned an invalid business or wire response."""

    def __init__(self) -> None:
        super().__init__(
            code="gateway.protocol_invalid",
            message="Memory gateway response is invalid",
            retryable=False,
        )


class GatewayConflictError(MemScopeError):
    """The Fake observed inconsistent reuse of a request or message identity."""

    def __init__(self) -> None:
        super().__init__(
            code="gateway.request_conflict",
            message="Memory gateway identity conflicts with existing data",
            retryable=False,
        )
