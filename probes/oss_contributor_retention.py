"""Feasibility probe: first-time contributor retention from git history.

Clones commit metadata only (no file contents) and prints the figures quoted
in catalog entry `oss-contributor-retention`.

Usage: python probes/oss_contributor_retention.py [--repo URL] [--data-dir DIR]
Needs: Python 3.11+, git. Network: github.com.
"""

import argparse
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEP = "\x1f"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="https://github.com/pandas-dev/pandas.git")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".cache/portfolio-atlas/git")
    args = parser.parse_args()
    clone = args.data_dir / (args.repo.rstrip("/").split("/")[-1].removesuffix(".git") + ".git")
    args.data_dir.mkdir(parents=True, exist_ok=True)
    if not clone.exists():  # --filter=tree:0 fetches commits only: fast, small
        subprocess.run(["git", "clone", "--quiet", "--bare", "--filter=tree:0", args.repo, str(clone)], check=True)

    fmt = SEP.join(["%H", "%an", "%ae", "%aI", "%(trailers:key=Co-authored-by,valueonly,separator=;)"])
    log = subprocess.run(["git", "log", args.branch, f"--format={fmt}"], cwd=clone, text=True, check=True,
                         capture_output=True).stdout
    commits = [line.split(SEP) for line in log.splitlines() if line]
    print(f"HEAD: {commits[0][0]}  commits on {args.branch}: {len(commits)}  "
          f"first: {commits[-1][3][:10]}  last: {commits[0][3][:10]}")

    emails_by_name = defaultdict(set)
    for _, name, email, _, _ in commits:
        emails_by_name[name].add(email.lower())
    print(f"Distinct author emails: {len({c[2].lower() for c in commits})}; "
          f"author names with >1 email: {sum(len(v) > 1 for v in emails_by_name.values())}")
    print(f"Commits from GitHub noreply addresses: {sum(c[2].lower().endswith('users.noreply.github.com') for c in commits)}")
    print(f"Commits with Co-authored-by trailers: {sum(bool(c[4]) for c in commits)}")
    botlike = Counter(c[2].lower() for c in commits if "bot" in c[2].lower() or "bot" in c[1].lower())
    print(f"All 'bot'-matching emails (check for false positives!): {botlike.most_common()}")
    has_mailmap = subprocess.run(["git", "cat-file", "-e", f"{args.branch}:.mailmap"], cwd=clone, capture_output=True).returncode == 0
    license_line = subprocess.run(["git", "show", f"{args.branch}:LICENSE"], cwd=clone, text=True, capture_output=True).stdout.split("\n")[0]
    print(f".mailmap on {args.branch}: {has_mailmap}; LICENSE first line: {license_line!r}")

    # Naive identity = lower-cased email, bots = anything matching 'bot'. Deliberately simple:
    # the probe shows feasibility; a real project should resolve identities properly.
    dates = defaultdict(list)
    for _, name, email, authored, _ in commits:
        if "bot" not in email.lower() and "bot" not in name.lower():
            dates[email.lower()].append(datetime.fromisoformat(authored).astimezone(timezone.utc))
    by_cohort = defaultdict(lambda: [0, 0])
    for ds in dates.values():
        ds.sort()
        first = ds[0]
        returned = any(first + timedelta(days=1) < d <= first + timedelta(days=365) for d in ds)
        by_cohort[first.year][0] += 1
        by_cohort[first.year][1] += returned
    print("Cohort year (UTC): newcomers, % with another commit 1-365 days after their first")
    for year, (n, back) in sorted(by_cohort.items()):
        print(f"  {year}: {n:4d}  {back / n:.1%}")


if __name__ == "__main__":
    main()
