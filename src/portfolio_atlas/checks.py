"""Re-check that every dataset source still exists and, where cheap, still has the expected columns.

This catches link rot and schema drift between full re-verifications. It downloads at most
64 KB per check. It is not a substitute for re-running the probe scripts.

Usage: portfolio-atlas-check   (exit code 1 if any check fails)
"""

from __future__ import annotations

import csv
import sys
import urllib.error
import urllib.request

from . import __version__
from .catalog import SourceCheck, load_catalog

MAX_BYTES = 65536


def run_check(check: SourceCheck, timeout: float = 30) -> tuple[bool, str]:
    request = urllib.request.Request(
        str(check.url),
        headers={"User-Agent": f"portfolio-atlas-check/{__version__}", "Range": f"bytes=0-{MAX_BYTES - 1}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            if check.kind == "reachable":
                return True, f"HTTP {resp.status}"
            first_line = resp.read(MAX_BYTES).decode("utf-8-sig", errors="replace").splitlines()[0]
    except (urllib.error.URLError, TimeoutError, IndexError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    header = next(csv.reader([first_line]))
    missing = [c for c in check.columns if c not in header]
    if missing:
        return False, f"missing columns: {', '.join(missing)}"
    return True, f"{len(header)} columns, all {len(check.columns)} expected present"


def main() -> None:
    failures = 0
    for entry in load_catalog():
        for dataset in entry.datasets:
            for check in dataset.checks:
                ok, detail = run_check(check)
                failures += not ok
                print(f"{'PASS' if ok else 'FAIL'}  {entry.id}  {check.kind}  {check.url}  {detail}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
