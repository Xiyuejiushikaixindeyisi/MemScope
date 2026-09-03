"""Deterministic MemOS-compatible model fixture used only by the B05 verifier."""

import os

from memscope.mock_model_api.app import create_mock_model_app

_DEFAULT_EXTRACTION = (
    '{"memory list":[{"key":"fixture","memory_type":"UserMemory",'
    '"tags":[],"value":"deterministic fixture memory"}],"summary":"fixture"}'
)

app = create_mock_model_app(
    chat_content=os.getenv("B05_MOCK_EXTRACTION_JSON", _DEFAULT_EXTRACTION),
    embedding_dimension=int(os.getenv("B05_MOCK_EMBEDDING_DIMENSION", "16")),
    timeout_delay_ms=int(os.getenv("B05_MOCK_TIMEOUT_DELAY_MS", "100")),
    chat_delay_ms=int(os.getenv("B05_MOCK_CHAT_DELAY_MS", "0")),
)
