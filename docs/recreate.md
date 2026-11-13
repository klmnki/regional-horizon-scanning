# Recreate the workflow

## 1. Choose the research runtime

Use a researcher or an assistant with web search and page-reading tools. The original implementation uses a recurring assistant prompt with Google Sheets and Gmail connectors. This kit is provider-independent: it supplies the operating method and archive format, not a hosted research service.

Start with a supervised manual run. No API key is required by the Python tools. Any assistant subscription, model API or connector has its own requirements and potential costs; the repository does not activate them.

## 2. Define the scope

Edit `config/region.json`. Keep a separate regional lane and research lane when adapting the country set. Set local language/script coverage, query seeds and source families. Verify actual source domains and relevance during each scan; a source list is a starting point, not a permanent endorsement.

The supplied profile follows six countries and the wider Europe and Central Asia region. It does not assert a current institutional office footprint or programme eligibility. The regional lane can include relevant places beyond the focal countries when the pathway is explicit.

## 3. Make your own register

Run:

```sh
python scanner.py init --out work/my-scan
```

This creates empty CSV templates for Signals, Analytical Products, Synthesis, Coverage and Candidates, plus a run scaffold. You can use them locally or import each CSV into a tab in a new Google Sheet. Keep headers unique; add filters, frozen headers, text wrapping and dropdowns if useful. Keep IDs and source links as text and use proper date cells for dates in Sheets.

The operational register uses 38 signal fields and 26 analytical-product fields. This kit preserves their meaning while using generic names for private project references. Its synthesis and coverage templates remove duplicated trailing headers observed in the inspected register. Existing records have not been copied.

Place your method and territory configuration in clearly named reference tabs or provide the repository files alongside the Sheet. Give the assistant access only to your intended register. Use a private, local setting for any register URL or recipient. Do not put those settings in Git.

The Python archive is an alternative local record, not a Google Sheets synchronisation client. Choose one authoritative working register. Avoid independently editing two archives and assuming they will merge automatically.

## 4. Run once and review

Generate a dated prompt:

```sh
python scanner.py prompt --date 2026-11-13 --out work/my-scan/daily-prompt.md
```

Give the prompt, method and relevant previous records to the research assistant. Supply the register destination privately. If using the local tool, ask for JSON matching `work/my-scan/run.json`; records use the exact column names in `schemas/registers.json`. `examples/run.json` shows a populated fictional run. The assistant must do live research before recording real observations.

For the first real run, review sources and at least one rejected candidate from each lane. Check that non-English coverage is real, global research has transfer limits, regional items state a pathway, and missing access is recorded. Read every selected item before sharing. The validator checks structure and consistency, not factual truth.

## 5. Add recurrence only after the first run works

Ask your assistant's supported automation interface to run the daily prompt at your chosen time and timezone. Configure it through that product's normal scheduling controls. This repository creates no recurring task and includes no scheduled GitHub research workflow.

The source workflow intends **08:00 Europe/Istanbul**. Verify the first trigger against the local clock: a scheduler may interpret an hour in UTC or another host timezone. This was a documented operational limitation in the related earlier sprint. Do not assume a recurrence string establishes correct local timing.

Pass the local date explicitly to `scanner.py prompt`. The CLI does not derive it from the machine timezone. Prevent overlapping runs in your scheduler. On retries, load today's existing state and resume only unfinished steps. The local archive refuses a changed payload for an already archived date and refuses duplicate evidence IDs or canonical keys across dates. It is append-only; corrections require a new, linked material-update record.

## 6. Enable delivery only if you want it

The default is a local draft. To add email, separately configure and authorize the exact account, recipient and recurrence in your assistant. Keep those settings outside this repository. The kit has no sending code.

Use a stable subject containing the local date. Save evidence first. After sending, verify the result and intended recipient privately. When the result is uncertain, check Sent for that subject/date/recipient before retrying. Record Sent, Failed or Uncertain based on evidence. Do not change sharing permissions or submit signals elsewhere as a side effect of a scan.

## 7. Keep learning from the archive

Use `prompts/review.md` within the same daily workflow for weekly and monthly reviews. Retain contradictions and expired interpretations. Revisit language, country, sector and institutional biases. Human review can reject, revise or retain records; being archived does not make an interpretation approved.
