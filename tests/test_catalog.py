from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from portfolio_atlas.catalog import Claim, Dataset, Feasibility, load_catalog, load_entries, search, to_markdown

REPO = Path(__file__).resolve().parents[1]
CATALOG = load_catalog()
ENTRY = CATALOG[0]


def ids(results):
    return [e.id for e in results]


# ------------------------------------------------------------ the shipped catalog


def test_catalog_has_unique_ids():
    assert len(CATALOG) >= 4
    assert len(set(ids(CATALOG))) == len(CATALOG)


@pytest.mark.parametrize("entry", CATALOG, ids=lambda e: e.id)
def test_probe_script_exists(entry):
    assert (REPO / entry.feasibility.probe.script).is_file()


@pytest.mark.parametrize("entry", CATALOG, ids=lambda e: e.id)
def test_every_dataset_has_a_source_check(entry):
    assert all(d.checks for d in entry.datasets)


@pytest.mark.parametrize("entry", CATALOG, ids=lambda e: e.id)
def test_every_claim_renders_with_its_own_status(entry):
    lines = to_markdown(entry).splitlines()
    for claim in entry.claims():
        [line] = [line for line in lines if line.endswith(claim.text)]
        assert line.startswith(f"- [{claim.status}"), line


@pytest.mark.parametrize("entry", CATALOG, ids=lambda e: e.id)
def test_no_stray_status_tags(entry):
    """Every status tag in the output belongs to a claim or license; nothing is silently upgraded."""
    text = to_markdown(entry)
    for status in ("verified", "reported", "unverified"):
        tagged = sum(c.status == status for c in entry.claims()) + sum(d.license.status == status for d in entry.datasets)
        fixed = {"verified": 2, "reported": 1, "unverified": 1}[status]  # legend, plus the probe-findings heading
        assert text.count(f"[{status}") == tagged + fixed, status


# ------------------------------------------------------------ schema rules


def test_reported_claim_needs_a_basis():
    with pytest.raises(ValidationError, match="needs a basis"):
        Claim(text="Updated weekly.", status="reported")


def test_dataset_without_a_verified_fact_is_rejected():
    data = ENTRY.datasets[0].model_dump(mode="json")
    data["facts"] = [{"text": "Probably has a date column.", "status": "unverified"}]
    with pytest.raises(ValidationError, match="no verified facts"):
        Dataset.model_validate(data)


def test_feasibility_needs_a_verified_supports_claim():
    data = ENTRY.feasibility.model_dump(mode="json")
    data["supports"] = [{"text": "Could support forecasting.", "status": "unverified"}]
    with pytest.raises(ValidationError, match="at least one 'supports' claim must be verified"):
        Feasibility.model_validate(data)


def test_entry_id_must_match_file_name(tmp_path):
    (tmp_path / "wrong-name.yaml").write_text(yaml.safe_dump(ENTRY.model_dump(mode="json")))
    with pytest.raises(ValueError, match="wrong-name.yaml: id .* must match the file name"):
        load_entries(tmp_path)


def test_invalid_entry_error_names_the_file(tmp_path):
    (tmp_path / "broken.yaml").write_text("id: broken\ntitle: only a title\n")
    with pytest.raises(ValueError, match="broken.yaml"):
        load_entries(tmp_path)


# ------------------------------------------------------------ search


@pytest.mark.parametrize(
    "query, best",
    [
        ("security", "kev-exploitation-lag"),
        ("vulnerabilities", "kev-exploitation-lag"),  # plural matches singular
        ("product analyst retention", "oss-contributor-retention"),
        ("energy time series", "caiso-net-load-ramp"),
        ("operations logistics", "citibike-station-imbalance"),
    ],
)
def test_search_ranks_the_obvious_match_first(query, best):
    assert ids(search(query, CATALOG))[0] == best


@pytest.mark.parametrize("query", ["", "*", "data analyst portfolio projects"])
def test_generic_query_lists_everything(query):
    assert ids(search(query, CATALOG)) == ids(CATALOG)


def test_no_match_returns_nothing():
    assert search("zzzz", CATALOG) == []


def test_title_match_outranks_body_match():
    # ids chosen so that the alphabetical tie-break would put the body match first
    in_title = ENTRY.model_copy(update={"id": "b", "title": "Zebra crossings"})
    in_body = ENTRY.model_copy(update={"id": "a", "summary": ENTRY.summary + " Zebra."})
    assert ids(search("zebra", (in_body, in_title))) == ["b", "a"]
