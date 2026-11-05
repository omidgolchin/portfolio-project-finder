"""End-to-end tests through a real MCP client: in-process, over stdio, and over Streamable HTTP."""

import json
import socket
import subprocess
import sys
import time

import pytest
from mcp import Client, StdioServerParameters

from pathlib import Path

from portfolio_atlas.catalog import REPO_URL, load_catalog
from portfolio_atlas.server import build_server, entry_url

pytestmark = pytest.mark.anyio
ALL_IDS = sorted(e.id for e in load_catalog())


@pytest.fixture
def anyio_backend():
    return "asyncio"


def payload(result):
    """The search/fetch convention: exactly one text item holding JSON, mirrored in structuredContent."""
    assert not result.is_error, result.content
    assert len(result.content) == 1 and result.content[0].type == "text"
    data = json.loads(result.content[0].text)
    assert data == result.structured_content
    return data


def test_citation_urls_point_at_files_in_this_repo():
    repo = Path(__file__).resolve().parents[1]
    for entry in load_catalog():
        url = entry_url(entry)
        assert url.startswith(f"{REPO_URL}/blob/main/")
        assert (repo / url.removeprefix(f"{REPO_URL}/blob/main/")).is_file(), url


async def test_exposes_only_read_only_search_and_fetch():
    async with Client(build_server()) as client:
        tools = (await client.list_tools()).tools
        assert sorted(t.name for t in tools) == ["fetch", "search"]
        assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools)
        assert "[verified]" in client.instructions


async def test_search_returns_id_title_url():
    async with Client(build_server()) as client:
        results = payload(await client.call_tool("search", {"query": "security"}))["results"]
        assert results[0]["id"] == "kev-exploitation-lag"
        assert all(set(r) == {"id", "title", "url"} and r["url"].startswith("https://") for r in results)
        everything = payload(await client.call_tool("search", {"query": ""}))["results"]
        assert sorted(r["id"] for r in everything) == ALL_IDS


async def test_fetch_returns_full_entry_with_status_tags():
    async with Client(build_server()) as client:
        doc = payload(await client.call_tool("fetch", {"id": "caiso-net-load-ramp"}))
        assert set(doc) == {"id", "title", "text", "url", "metadata"}
        assert doc["text"].startswith(f"# {doc['title']}")
        assert "[verified]" in doc["text"] and "[reported: PUDL data dictionary]" in doc["text"]
        assert doc["metadata"]["verified_on"] == "2026-11-05"
        assert doc["metadata"]["claim_status_counts"]["verified"] > 0


async def test_fetch_unknown_id_is_a_helpful_error():
    async with Client(build_server()) as client:
        result = await client.call_tool("fetch", {"id": "titanic-survival"})
        assert result.is_error
        assert "kev-exploitation-lag" in result.content[0].text


async def test_stdio_entry_point():
    params = StdioServerParameters(command=sys.executable, args=["-m", "portfolio_atlas.server"])
    async with Client(params) as client:
        results = payload(await client.call_tool("search", {"query": ""}))["results"]
        assert sorted(r["id"] for r in results) == ALL_IDS


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def http_server():
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "portfolio_atlas.server", "--http", "--port", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("HTTP server did not start")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


async def test_streamable_http_entry_point(http_server):
    async with Client(http_server) as client:
        doc = payload(await client.call_tool("fetch", {"id": "oss-contributor-retention"}))
        assert "Fields observed in the data" in doc["text"]
