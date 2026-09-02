"""Apply the reusable Memory Gateway contract to the in-process Fake."""

from memscope.memory_gateway import FakeMemoryGateway, MemoryGateway
from tests.contract.memory_gateway_contract import assert_memory_gateway_contract


async def _factory() -> MemoryGateway:
    return FakeMemoryGateway()


async def test_fake_satisfies_memory_gateway_contract() -> None:
    await assert_memory_gateway_contract(_factory)
