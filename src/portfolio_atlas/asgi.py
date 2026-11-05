"""ASGI entry point for hosting the server over HTTP.

Vercel imports it from the repository root as `src.portfolio_atlas.asgi:app` (see `[tool.vercel]`
in pyproject.toml). With the package installed, any ASGI server works too:

    uvicorn portfolio_atlas.asgi:app
"""

from .server import http_app

app = http_app()
