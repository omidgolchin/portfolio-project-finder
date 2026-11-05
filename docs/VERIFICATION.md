# Verification standard

The catalog is only useful if its claims can be trusted. This page defines what "verified" means and
what a new entry needs before it is merged.

## Statuses

| Status | Meaning | Example |
|---|---|---|
| `verified` | Checked directly against the data, or the publisher's own files, on the entry's `verified_on` date | "1,768 entries; cveID is unique" after loading the CSV |
| `reported` | Stated by a named source but not independently tested; `basis` must name the source | "Updated on weekdays" from a README |
| `unverified` | Plausible but not checked; `basis` says why it is unchecked | "Weather join would explain demand swings" |

Fields go in `fields_observed` only if you saw them in the data. A field mentioned only in
documentation is a `reported` fact, not an observed field.

"Why employers may care" and "How it differs" are editorial judgement and are rendered as such. Keep
them to reasoning; don't invent statistics such as "80% of employers want X".

## What the schema enforces

Loading fails if:

- a `reported` claim has no `basis`;
- a dataset has no `verified` fact, or no observed fields;
- an entry's feasibility has no `verified` "supports" claim, or its probe has no findings;
- an entry's `id` doesn't match its file name.

The tests also check that every claim renders with its own status, so nothing is silently upgraded,
and that every probe script exists.

## Checklist for a new entry

1. Get the data from the publisher's own distribution (or an official mirror), not a re-upload.
2. Write a probe in `probes/` that downloads the data into a fresh directory and prints every number
   the entry quotes. Run it from scratch, not against files you've already been working with.
3. Record the data snapshot (release, commit or file name) and the run date in `feasibility.probe`.
4. Tag every fact. If you couldn't read the license yourself, it is `reported` or `unverified`.
5. Add at least one `checks` item per dataset (`reachable`, or `csv_header` with expected columns).
6. Run `uv run --extra dev pytest` and `uv run portfolio-atlas-check`.

## What probes caught in the first four entries

Re-running the analysis as a clean, reproducible script found problems an ad-hoc pass missed or got
wrong:

- **Citi Bike:** the first ad-hoc estimate of daily rebalancing need was about 6,470 bikes. The
  probe showed that raw station IDs split stations (`6098.10` vs `6098.1` in the source) and that
  trips ending after midnight added a stray day. The defensible figure, keyed by station name, is
  about 4,662.
- **Citi Bike:** the April 2026 zip is a third the size of its neighbours, which looked like missing
  data, but the month is complete. File size is not a completeness check.
- **EIA-930 (PUDL):** the `imputed` column, which sounds like the clean choice, is almost empty in
  the by-fuel table. CAISO's battery categories are empty too, which rules out a tempting extension.
- **pandas git history:** cohort counts shifted at year boundaries depending on whether dates were
  taken in UTC or authors' local time. The probe now uses UTC.
- **KEV:** the CSV encodes `forensicTriage` as `Yes`/`No`, which some tools silently cast to boolean.
