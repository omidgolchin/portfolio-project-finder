# Portfolio Atlas

A small, curated catalog of data-analysis portfolio projects for aspiring analysts, where every
dataset has actually been downloaded, inspected and test-analysed. AI assistants (Claude, ChatGPT)
can query it through the [Model Context Protocol](https://modelcontextprotocol.io), so their project
suggestions rest on checked facts instead of familiar guesses.

It complements an assistant rather than replacing it: the assistant still tailors advice to the
person, but it can cite what is known about the data, what isn't, and when it was last checked.

## Why

Ask an LLM for portfolio ideas and you tend to get the same handful (Titanic, Olist, Superstore),
with field names, data availability and feasibility taken on trust. During testing, when this
server failed to start, Claude fell back to suggesting the Olist dataset from memory, with no
verification. That gap is what this project fills.

## What's in the catalog

| Entry | Roles | Data | Something you only learn by checking |
|---|---|---|---|
| `kev-exploitation-lag` | Security, risk/GRC | CISA KEV + CVE List | 62 KEV entries were listed *before* their CVE record was published; in 2026 most remediation deadlines dropped from 21 days to 3 |
| `oss-contributor-retention` | Product analyst | git history (pandas) | 208 author names appear with several emails; a naive "bot" filter removes real people |
| `citibike-station-imbalance` | Operations, logistics | Citi Bike trips | The source writes the same station's ID as `6098.10` and `6098.1`; keying on raw IDs overstates imbalance by 43% |
| `caiso-net-load-ramp` | Energy, time series | EIA-930 via PUDL | The "imputed" column is almost empty, and California's April duck-curve trend reverses in 2026 |

Each entry covers: the questions to investigate; why employers may care and how it differs from
common projects (both marked as editorial judgement); datasets with access, license and *observed*
fields; feasibility with probe results and known limits; preparation steps and pitfalls; and a
suggested minimum deliverable. The entries live in
[`src/portfolio_atlas/opportunities/`](src/portfolio_atlas/opportunities/).

## How verification works

Every factual claim carries a status, enforced by the schema rather than by convention:

- **verified**: checked directly against the data or the publisher's own files on the entry's date
- **reported**: stated by a named source (docs, README) but not independently tested
- **unverified**: plausible but not checked (typical for extension ideas)

Each entry has a **probe script** in [`probes/`](probes/) that downloads the data and reproduces
every number the entry quotes, so anyone can re-run it. A cheap **source check**
(`portfolio-atlas-check`) confirms that files still exist and CSV headers still match.
[docs/VERIFICATION.md](docs/VERIFICATION.md) sets out the standard for adding entries.

## Use it

### Hosted server (nothing to install)

`https://portfolio-project-finder.vercel.app/mcp` is public, read-only and needs no authentication.

- **claude.ai:** Customize → Connectors → Add custom connector. Enter a name (e.g. `Portfolio Atlas`)
  and the URL above, leave authentication empty, then switch the connector on in a chat. Tested on
  2026-11-05.
- **ChatGPT** (paid plans): Settings → Apps & Connectors → Advanced → turn on Developer mode, then
  create a connector with the URL above and "No authentication". Not tested yet.
- **Claude Code:** `claude mcp add --transport http portfolio-atlas https://portfolio-project-finder.vercel.app/mcp`.
  Not tested against the hosted server.

Then ask, for example: *"Use Portfolio Atlas to suggest a project for an operations analyst role,
and tell me which claims are verified."*

### Run it locally

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). No clone is needed: `uvx` installs
the server straight from this repository.

**Claude Code** (tested with Claude Code 2.1.318):

```bash
claude mcp add portfolio-atlas -- uvx --from git+https://github.com/omidgolchin/portfolio-project-finder portfolio-atlas
```

If you have a local clone, use `uv run --directory /absolute/path/to/portfolio-project-finder portfolio-atlas`
as the command instead.

**Claude Desktop**: add this to `claude_desktop_config.json` (not tested here; you may need the
full path to `uvx`):

```json
{
  "mcpServers": {
    "portfolio-atlas": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/omidgolchin/portfolio-project-finder", "portfolio-atlas"]
    }
  }
}
```

**Your own HTTP server:** `portfolio-atlas --http --host 0.0.0.0 --port 8000` serves the same app as
the hosted one at `/mcp`; any ASGI server can also run `portfolio_atlas.asgi:app`.

**Any MCP client**, e.g. the MCP Inspector CLI:

```bash
npx @modelcontextprotocol/inspector --cli uvx --from git+https://github.com/omidgolchin/portfolio-project-finder portfolio-atlas --method tools/call --tool-name search --tool-arg query=energy
```

### Tools

| Tool | Input | Output |
|---|---|---|
| `search` | `query` (keywords; empty lists everything) | `{"results": [{"id", "title", "url"}]}` |
| `fetch` | `id` | `{"id", "title", "text", "url", "metadata"}`, where `text` is the full entry as Markdown with a status tag on every claim |

Both are read-only. The shapes follow the `search`/`fetch` convention OpenAI documents for ChatGPT
connectors and deep research. Claude accepts any tools, so one server serves both.

## Development

```bash
uv run --extra dev pytest                                          # schema rules, rendering, search; MCP in-process, over stdio and over HTTP
uv run portfolio-atlas-check                                       # are the sources still there, with the expected columns?
uv run --extra probes python probes/citibike_station_imbalance.py  # re-derive an entry's numbers (downloads data)
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the tests on Python 3.11 to 3.14
and runs the source check weekly.

## Design decisions

- **Data in YAML in the repository, validated with Pydantic.** No database: a curated catalog of
  tens of entries doesn't need one, and git history is the audit trail.
- **MCP only, with two tools.** MCP is the integration standard both Claude and ChatGPT support. A
  separate REST API or website would add a second interface with no current user.
- **Keyword search, not embeddings.** At this size, transparent ranking beats semantic search, and
  it costs nothing.
- **Verification in the schema.** A dataset without a verified fact, or a "reported" claim without
  a source, fails to load.
- **Hosted on Vercel's free Hobby plan.** The HTTP app is stateless, so any serverless instance can
  answer any request. Vercel loads `src.portfolio_atlas.asgi:app` (set in `pyproject.toml`) and
  redeploys on every push to `main`.

## What remains before offering it publicly

1. **Test more widely.** The hosted server has been tried with one prompt as a claude.ai custom
   connector; ChatGPT developer mode is untested. Keep an eye on the Vercel project's usage page,
   since the free plan has usage limits.
2. **Fill domain gaps with the same rigor.** Healthcare (CMS), finance (SEC EDGAR, CFPB, HMDA),
   HR and wages (DOL H-1B disclosures) and marketing analytics are common analyst domains, but
   those publishers were blocked by the build environment's network policy, so nothing was verified
   for them.
3. **Second-person review.** Someone other than the author should re-run each probe before an
   entry is called verified.
4. **Read the remaining terms in full:** the Citi Bike Data License Agreement and the CVE Program
   Terms of Use are currently only "reported".
5. **Choose content licensing.** Code and catalog are both MIT for now; CC BY 4.0 is the usual
   choice for written content.
6. **Set a freshness policy**, e.g. re-run probes quarterly and flag entries older than six months.
   The weekly check only detects missing files or columns.
7. **Add a feedback channel** (GitHub issues or discussions) to learn which entries people pick and
   where they get stuck.

## License

MIT, see [LICENSE](LICENSE). Datasets keep their own licenses, listed in each entry.
