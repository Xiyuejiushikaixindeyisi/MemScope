"""Lifespan-owned resource composition for delivered application profiles."""

from dataclasses import dataclass

from memscope.application.memory_operations import MemoryOperations
from memscope.memory_gateway.memos import MemosMemoryGateway
from memscope.memory_gateway.receipt_store import GatewayReceiptStore
from memscope.raw_store.sqlite import SqliteRawStore
from memscope.settings import AppProfile, AppSettings


@dataclass(slots=True)
class RuntimeResources:
    """Resources opened for one ASGI lifespan."""

    operations: MemoryOperations
    raw_store: SqliteRawStore
    gateway: MemosMemoryGateway

    async def close(self) -> None:
        """Close in reverse construction order."""

        await self.gateway.close()
        await self.raw_store.close()


async def open_runtime(settings: AppSettings) -> RuntimeResources:
    """Open the exact runtime selected by a validated profile."""

    if settings.app_profile is not AppProfile.MEMOS_ADD or settings.memos_base_url is None:
        raise ValueError("memos_add runtime requires its validated profile")
    raw_store = await SqliteRawStore.open(
        settings.database_path,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
    )
    receipt_store: GatewayReceiptStore | None = None
    gateway: MemosMemoryGateway | None = None
    try:
        receipt_store = await GatewayReceiptStore.open(
            settings.memos_gateway_receipt_path,
            busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        )
        gateway = MemosMemoryGateway(
            base_url=settings.memos_base_url,
            receipt_store=receipt_store,
            connect_timeout_seconds=settings.memos_connect_timeout_seconds,
            response_max_bytes=settings.memos_response_max_bytes,
        )
        await gateway.verify_upstream(
            timeout_seconds=min(
                settings.memos_connect_timeout_seconds + 2,
                settings.add_deadline_seconds - settings.memos_deadline_reserve_seconds,
            )
        )
        operations = MemoryOperations(
            raw_store=raw_store,
            gateway=gateway,
            add_deadline_seconds=settings.add_deadline_seconds,
            add_warn_seconds=settings.add_warn_seconds,
            gateway_reserve_seconds=settings.memos_deadline_reserve_seconds,
        )
        return RuntimeResources(operations=operations, raw_store=raw_store, gateway=gateway)
    except BaseException:
        if gateway is not None:
            await gateway.close()
        elif receipt_store is not None:
            await receipt_store.close()
        await raw_store.close()
        raise
