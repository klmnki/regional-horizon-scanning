# Local data and commands

Run commands from the repository root with Python 3.11+. The tool uses only the standard library. Configuration options go before the command, for example `python scanner.py --config config/region.json validate work/run.json`.

| Command | Result |
| --- | --- |
| `init --out work/my-scan` | Creates a new directory with blank CSV headers and an intentionally incomplete JSON scaffold |
| `prompt --date YYYY-MM-DD --out work/daily-prompt.md` | Combines the research prompt, local date and regional configuration |
| `demo --out work/demo` | Creates the fictional run, CSVs and an evidence digest |
| `validate work/run.json` | Checks structural consistency; nonzero exit on failure |
| `brief work/run.json --out work/briefing.md` | Validates and renders an evidence digest; refuses to overwrite |
| `archive work/run.json --archive work/archive` | Validates and atomically appends to a local SQLite archive |

`init`, `demo` and `prompt` refuse to overwrite existing outputs. Choose a fresh output path when repeating a demo. The scaffold deliberately has no run date or coverage: it cannot pass validation until you supply actual research state. The bundled demo uses the supplied eight-lane configuration; customised lanes require your own example/run.

## Run structure

See `examples/run.json`. Top-level keys are `schema_version: 1`, `run_date` (ISO local date), `example` (boolean), and five lists: `signals`, `products`, `synthesis`, `coverage`, `candidates`.

Each signal or product has:

```json
{
  "lane": "ECA",
  "canonical_key": "an-underlying-event-or-paper-version",
  "fields": { "Signal ID": "SIG-20261113-ECA-01" }
}
```

The abbreviated `fields` object above must be expanded to **all** headers for its register in `schemas/registers.json`. Other lists contain row objects directly, using their full headers. Blank/unknown cells use `""`, not zero or a made-up date. Signal scores use integer `Score /10` and a JSON string in `Score breakdown` with relevance, novelty, importance, distribution and evidence components. Ranks are consecutive integers within a lane. Dates use YYYY-MM-DD; event/data period can be explanatory text.

Use a stable canonical key based on the underlying development, actor and version, not a news URL. Translations and syndicated reports share a key. A material update gets a new version key and links the earlier evidence ID in Related IDs. The tool cannot discover semantic duplicates; a researcher must assign the keys correctly.

The coverage `Run ID` is `YYYY-MM-DD-LANE`. `Lane` is the configured display name. All lanes need one row, including failed or empty searches. Candidate counts include assessed leads; selected counts and record IDs must match the saved evidence. Candidate rows are optional in the local JSON but keeping selection/rejection reasons is part of the research method.

## Checks and limits

The validator checks dates, record identifiers, field names, source URL shape, selected-signal score ranges, required evidence descriptions, transfer-test presence, per-lane limits, duplicate canonical keys, and coverage counts/statuses. It permits unknown publication dates and explicitly incomplete runs so failures can be honestly archived.

It does **not** open sources, verify claims or language coverage, judge whether a regional pathway is convincing, establish independence, validate all synthesis links against history, enforce evidence-stage semantics, or calculate analytical-product scores. Synthesis/candidate rows receive schema checks only. Those tasks remain with the researcher and reviewer. A structurally valid run is not proof of a successful search or permission to publish.

The example flag labels demonstrations and allows reserved example URLs. It is not a security boundary; review all data before sharing. CSV exports prefix potentially executable formula text with an apostrophe. JSON preserves original text.

## Archive and recovery

`archive.sqlite3` stores each validated run as JSON plus its SHA-256 digest, and indexes evidence IDs and canonical keys. A transaction makes the append atomic. The same payload/date is a no-op. A different payload for an existing date is refused; duplicate IDs or canonical keys across days roll back the new run. Concurrent writers use SQLite's transaction lock.

This local append-only archive is a simple reproducibility aid. It deliberately differs from the original mutable Sheets workflow: keep partial work outside the archive while resuming it; after archiving, preserve the record and document corrections as linked updates in a later run. Do not delete or silently rewrite a run to make it appear complete.

The tool does not send, schedule or synchronise anything. Its briefing is a structured digest, not an automatically generated cross-country analysis. The prompt guides the researcher in adding the final interpretation and grounded question.
