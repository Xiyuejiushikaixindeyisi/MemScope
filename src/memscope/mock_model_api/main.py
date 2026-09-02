"""Default no-key Mock Model ASGI entry point."""

from memscope.mock_model_api.app import create_mock_model_app

app = create_mock_model_app()
