"""MCP server exposing the catalog as two read-only tools, `search` and `fetch`.

The tool names and result shapes follow the search/fetch convention OpenAI documents for
ChatGPT connectors and deep research; Claude can use any tools, so one shape serves both.

Run locally (stdio):            portfolio-atlas
Run as an HTTP server:          portfolio-atlas --http [--host 127.0.0.1] [--port 8000]
"""

from __future__ import annotations

import argparse
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from typing_extensions import TypedDict  # typing.TypedDict breaks pydantic schemas before Python 3.12

from . import __version__
from .catalog import REPO_URL, Opportunity, load_catalog, search as search_catalog, to_markdown

INSTRUCTIONS = """\
Portfolio Atlas is a small, curated catalog of data-analysis portfolio project opportunities whose
datasets were downloaded and inspected, and whose core analysis was test-run, by the maintainers.
Use `search` to find entries (an empty query lists all) and `fetch` to read one in full.

When you use an entry:
- Keep the status tags. [verified] claims were checked against the data on the stated date;
  [reported] claims come from the named source and were not tested; [unverified] claims are
  plausible but unchecked. Never present a [reported] or [unverified] claim as verified.
- Mention the verification date. Data changes, so recommend re-running the entry's probe script.
- Treat "Why employers may care" and "How it differs" as editorial judgement, not fact.
- The catalog is deliberately small. If nothing fits the user, say so, then help with your own
  ideas while making clear those ideas have not been verified.
"""

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class SearchHit(TypedDict):
    id: str
    title: str
    url: str


class SearchResults(TypedDict):
    results: list[SearchHit]


class Document(TypedDict):
    id: str
    title: str
    text: str
    url: str
    metadata: dict[str, Any]


def entry_url(entry: Opportunity) -> str:
    """Citation URL: the entry's source file in the public repository."""
    return f"{REPO_URL}/blob/main/src/portfolio_atlas/opportunities/{entry.id}.yaml"


def build_server(entries: tuple[Opportunity, ...] | None = None) -> MCPServer:
    catalog = entries if entries is not None else load_catalog()
    by_id = {e.id: e for e in catalog}
    server = MCPServer("portfolio-atlas", title="Portfolio Atlas", instructions=INSTRUCTIONS, version=__version__)

    @server.tool(annotations=READ_ONLY)
    def search(query: str) -> SearchResults:
        """Search verified data-analysis portfolio project opportunities.

        Matches keywords against titles, target roles, skills, domains, questions and dataset names,
        e.g. "product analyst retention", "energy time series", "security". An empty query lists all
        entries. Returns ids to pass to `fetch`.
        """
        return {"results": [{"id": e.id, "title": e.title, "url": entry_url(e)} for e in search_catalog(query, catalog)]}

    @server.tool(annotations=READ_ONLY)
    def fetch(id: str) -> Document:
        """Fetch one project opportunity in full, as Markdown with a verification status on every claim:
        datasets and access, licenses, fields observed, preparation effort and pitfalls, feasibility
        probe results, limits and suggested scope."""
        entry = by_id.get(id)
        if entry is None:
            raise ToolError(f"Unknown id {id!r}. Valid ids: {', '.join(sorted(by_id))}")
        metadata = {
            "verified_on": entry.verified_on.isoformat(),
            "roles": entry.roles,
            "skills": entry.skills,
            "domains": entry.domains,
            "preparation_effort": entry.preparation.effort,
            "datasets": [{"name": d.name, "landing_url": str(d.landing_url), "license": d.license.name} for d in entry.datasets],
            "claim_status_counts": {s: sum(c.status == s for c in entry.claims()) for s in ("verified", "reported", "unverified")},
        }
        return {"id": entry.id, "title": entry.title, "text": to_markdown(entry), "url": entry_url(entry), "metadata": metadata}

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="portfolio-atlas", description=__doc__.splitlines()[0])
    parser.add_argument("--http", action="store_true", help="serve Streamable HTTP at /mcp instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    server = build_server()
    if args.http:
        server.run("streamable-http", host=args.host, port=args.port)
    else:
        server.run()


if __name__ == "__main__":
    main()
