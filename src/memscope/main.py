"""Default ASGI entry point used by Uvicorn."""

from memscope.app import create_app

app = create_app()
