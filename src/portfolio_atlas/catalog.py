"""The catalog: schema, loading, search and Markdown rendering.

Every factual statement in an entry carries a verification status, so that
neither a person nor an AI assistant can mistake an assumption for a checked fact:

- verified:   checked directly against the data or the publisher's own files
              on the entry's verification date.
- reported:   stated by a named source (docs, README, search excerpt), not tested.
- unverified: plausible but not checked.
"""

from __future__ import annotations

import re
from datetime import date
from functools import cache
from importlib.resources import files
from typing import TYPE_CHECKING, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable

REPO_URL = "https://github.com/omidgolchin/portfolio-project-finder"

Status = Literal["verified", "reported", "unverified"]

LEGEND = (
    "Status tags: [verified] = checked directly against the data or the publisher's own files on the "
    "verification date; [reported] = stated by the named source but not independently tested; "
    "[unverified] = plausible but not checked. 'Why employers may care' and 'How it differs' are "
    "editorial judgement, not verified facts."
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Claim(_Model):
    text: str
    status: Status
    basis: str | None = None  # where a claim was reported, or how it was checked

    @model_validator(mode="after")
    def _reported_needs_basis(self) -> Claim:
        if self.status == "reported" and not self.basis:
            raise ValueError(f"'reported' claim needs a basis (who reported it): {self.text!r}")
        return self


class License(_Model):
    name: str
    url: HttpUrl | None = None
    status: Status
    basis: str | None = None
    note: str | None = None


class SourceCheck(_Model):
    """A cheap, repeatable check that a source still looks the way the entry says."""

    url: HttpUrl
    kind: Literal["reachable", "csv_header"]
    columns: list[str] = []


class Dataset(_Model):
    name: str
    publisher: str
    landing_url: HttpUrl
    access: str
    format: str
    license: License
    fields_observed: list[str] = Field(min_length=1)  # only names seen in the actual data
    facts: list[Claim] = Field(min_length=1)
    checks: list[SourceCheck] = []

    @model_validator(mode="after")
    def _has_verified_fact(self) -> Dataset:
        if not any(f.status == "verified" for f in self.facts):
            raise ValueError(f"dataset {self.name!r} has no verified facts; it does not belong in the catalog yet")
        return self


class Differentiation(_Model):
    common_version: str
    how_this_differs: str


class Preparation(_Model):
    effort: Literal["low", "medium", "high"]
    effort_note: str
    steps: list[str] = Field(min_length=1)
    pitfalls: list[str] = Field(min_length=1)


class Probe(_Model):
    script: str  # path relative to the repository root
    run_on: date
    data_snapshot: str
    findings: list[str] = Field(min_length=1)


class Feasibility(_Model):
    supports: list[Claim] = Field(min_length=1)
    limits: list[str] = Field(min_length=1)
    probe: Probe

    @model_validator(mode="after")
    def _probe_backs_a_claim(self) -> Feasibility:
        if not any(c.status == "verified" for c in self.supports):
            raise ValueError("at least one 'supports' claim must be verified by the probe")
        return self


class Scope(_Model):
    minimum_deliverable: list[str] = Field(min_length=1)
    extensions: list[Claim] = []


class Opportunity(_Model):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str
    summary: str
    verified_on: date
    roles: list[str] = Field(min_length=1)
    skills: list[str] = Field(min_length=1)
    domains: list[str] = Field(min_length=1)
    questions: list[str] = Field(min_length=1)
    employer_relevance: str
    differentiation: Differentiation
    datasets: list[Dataset] = Field(min_length=1)
    preparation: Preparation
    feasibility: Feasibility
    scope: Scope

    def claims(self) -> list[Claim]:
        return [f for d in self.datasets for f in d.facts] + list(self.feasibility.supports) + list(self.scope.extensions)


# ---------------------------------------------------------------- loading


def load_entries(directory: Traversable) -> tuple[Opportunity, ...]:
    """Load and validate every *.yaml entry in a directory, sorted by file name."""
    entries = []
    for path in sorted(directory.iterdir(), key=lambda p: p.name):
        if not path.name.endswith(".yaml"):
            continue
        try:
            entry = Opportunity.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except ValueError as exc:  # pydantic's ValidationError is a ValueError
            raise ValueError(f"{path.name}: {exc}") from exc
        if entry.id != path.name.removesuffix(".yaml"):
            raise ValueError(f"{path.name}: id {entry.id!r} must match the file name")
        entries.append(entry)
    return tuple(entries)


@cache
def load_catalog() -> tuple[Opportunity, ...]:
    """The catalog shipped inside the package."""
    return load_entries(files("portfolio_atlas").joinpath("opportunities"))


# ---------------------------------------------------------------- search

_STOPWORDS = {"a", "an", "and", "the", "of", "for", "to", "in", "on", "with", "project", "projects", "data", "i", "me", "my", "want", "ideas", "analyst", "analysis", "portfolio", "dataset"}


def _stem(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(text: str) -> set[str]:
    return {_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS}


def search(query: str, entries: tuple[Opportunity, ...]) -> list[Opportunity]:
    """Keyword search, weighted toward titles and tags. An empty query (or '*') lists everything.

    Deliberately simple: the catalog is small and curated, so transparent ranking beats embeddings.
    """
    wanted = _tokens(query)
    if not wanted:
        return list(entries)
    scored = []
    for e in entries:
        fields = [
            (3, e.title),
            (2, " ".join(e.roles + e.skills + e.domains)),
            (1, " ".join([e.summary, *e.questions, *(f"{d.name} {d.publisher}" for d in e.datasets)])),
        ]
        score = sum(weight * len(wanted & _tokens(text)) for weight, text in fields)
        if score:
            scored.append((-score, e.id, e))
    return [e for *_, e in sorted(scored)]


# ---------------------------------------------------------------- rendering


def _tag(status: Status, basis: str | None) -> str:
    return f"[{status}: {basis}]" if basis else f"[{status}]"


def _claim(c: Claim) -> str:
    return f"- {_tag(c.status, c.basis)} {c.text}"


def to_markdown(e: Opportunity) -> str:
    """Render one entry as self-contained Markdown, with a status tag on every factual claim."""
    lines = [
        f"# {e.title}",
        f"id: `{e.id}` | verified on {e.verified_on.isoformat()} | data preparation effort: {e.preparation.effort}",
        "",
        LEGEND,
        "",
        e.summary.strip(),
        "",
        "## Roles and skills",
        f"- Roles: {', '.join(e.roles)}",
        f"- Skills demonstrated: {', '.join(e.skills)}",
        f"- Domains: {', '.join(e.domains)}",
        "",
        "## Questions to investigate",
        *(f"- {q}" for q in e.questions),
        "",
        "## Why employers may care (editorial judgement)",
        e.employer_relevance.strip(),
        "",
        "## How it differs from common projects (editorial judgement)",
        f"- Common version: {e.differentiation.common_version.strip()}",
        f"- This project: {e.differentiation.how_this_differs.strip()}",
        "",
        "## Data",
    ]
    for d in e.datasets:
        lic = d.license
        license_line = f"- License: {lic.name}" + (f" ({lic.url})" if lic.url else "") + f" {_tag(lic.status, lic.basis)}"
        lines += [
            "",
            f"### {d.name}",
            f"- Publisher: {d.publisher}",
            f"- Landing page: {d.landing_url}",
            f"- Access: {d.access.strip()}",
            f"- Format: {d.format}",
            license_line + (f" {lic.note.strip()}" if lic.note else ""),
            f"- Fields observed in the data: {', '.join(f'`{f}`' for f in d.fields_observed)}",
            *(_claim(f) for f in d.facts),
        ]
    p = e.feasibility.probe
    lines += [
        "",
        "## Feasibility",
        "What the data supports:",
        *(_claim(c) for c in e.feasibility.supports),
        "",
        "Known limits:",
        *(f"- {x}" for x in e.feasibility.limits),
        "",
        f"Probe: `{p.script}` ({REPO_URL}/blob/main/{p.script}), run on {p.run_on.isoformat()} "
        f"against {p.data_snapshot}. Findings [verified]:",
        *(f"- {x}" for x in p.findings),
        "",
        f"## Data preparation (effort: {e.preparation.effort})",
        e.preparation.effort_note.strip(),
        "",
        "Steps:",
        *(f"{i}. {s}" for i, s in enumerate(e.preparation.steps, 1)),
        "",
        "Pitfalls:",
        *(f"- {x}" for x in e.preparation.pitfalls),
        "",
        "## Suggested scope",
        "Minimum deliverable:",
        *(f"- {x}" for x in e.scope.minimum_deliverable),
    ]
    if e.scope.extensions:
        lines += ["", "Possible extensions:", *(_claim(c) for c in e.scope.extensions)]
    return "\n".join(lines) + "\n"
