"""Deterministic no-key Mock Model API."""

from memscope.mock_model_api.app import create_mock_model_app
from memscope.mock_model_api.deterministic import deterministic_embedding

__all__ = ["create_mock_model_app", "deterministic_embedding"]
