"""ASGI entry point for hosting the server over HTTP.

Vercel loads it through `[tool.vercel] entrypoint` in pyproject.toml. Any ASGI server works too:

    uvicorn portfolio_atlas.asgi:app
"""

from .server import http_app

app = http_app()
