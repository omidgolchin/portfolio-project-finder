import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from portfolio_atlas.catalog import SourceCheck
from portfolio_atlas.checks import run_check


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def base_url(tmp_path):
    (tmp_path / "trips.csv").write_text("ride_id,started_at,end_station_id\nA1,2026-04-01,6098.10\n")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_csv_header_passes_when_expected_columns_present(base_url):
    ok, detail = run_check(SourceCheck(url=f"{base_url}/trips.csv", kind="csv_header", columns=["ride_id", "started_at"]))
    assert ok, detail


def test_csv_header_reports_missing_columns(base_url):
    ok, detail = run_check(SourceCheck(url=f"{base_url}/trips.csv", kind="csv_header", columns=["ride_id", "birth year"]))
    assert not ok and detail == "missing columns: birth year"


def test_reachable(base_url):
    assert run_check(SourceCheck(url=f"{base_url}/trips.csv", kind="reachable"))[0]


def test_missing_file_fails(base_url):
    ok, detail = run_check(SourceCheck(url=f"{base_url}/gone.zip", kind="reachable"))
    assert not ok and "404" in detail
