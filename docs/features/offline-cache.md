# Diki cache and background preparation

Last updated: 2026-11-23.

Specification status: first 100 pending entries per file, buffer-first priority,
one-time existing-note HTML inventory, and rolling-snapshot retention confirmed.
Automatic remote scheduling is implemented; worker rollout and actual full
inventory population are separate operational steps.

Implementation status: shared raw-HTML/audio caching, list-driven prefetch, strict
offline mode, and coverage reporting exist. The current prefetch entry point
does not discover vocabulary directly from existing Anki notes.

Since 2026-11-22, cache paths are under `ANKI_FACTORY_DATA_DIR/diki_cache/`.
Both HTML and MP3 snapshots, together with `index.sqlite3`, are deliberately
versioned in the separate data repository. Browser/CLI/background defaults now
share centralized paths; independent cache/list environment variables were retired.
See [data storage and migration](data-storage.md). Resource selection, snapshot
retention, and interactive/background request isolation remain unchanged.

The optional [remote downloader](remote-downloads.md) shares the Mac cache and owns
a separate durable remote queue/budgets. Its original manual path was verified live.
Automatic scheduling now submits bounded source windows, fills missing inventory
HTML, and performs one startup drain with immediate background import/ACK. See
[ADR 0009](../decisions/0009-remote-preparation-scheduling.md).

## Purpose 1: process pending words offline

Originally, the app fetched Diki HTML and MP3 during each word's processing. This
made word creation dependent on internet access even after the browser UI existed.

The owner's first motivation for background preparation was to process words from
the pending queues without an internet connection. Download source material in
advance, then use it locally when selecting translations and adding notes.

This is offline independence from Diki for prepared vocabulary. Local Anki still
needs to be running to receive notes. Optional LLM calls and AnkiWeb sync are
separate network-dependent services; they are not what the local cache provides.
Audio remains an enrichment to the core vocabulary result, as established in
[project scope](../project.md).

## Purpose 2: reusable data for existing-note refinement

The cache should accumulate source material over time for words already in Anki,
not only the pending main/book queues.

The owner wants to define field contracts and evaluate/refine manually authored
older notes. Checking English and Polish **Diki compatibility** requires the
relevant source HTML: determine the dictionary headword and compare the extracted
Polish alternatives with stored content.

Repeated checks, tests, and future refinement work should reuse downloaded HTML
instead of downloading it on every run. Retaining raw source allows changed parser
or contract logic to run against the same local material. The one-time existing-note
backlog requests HTML only; recordings are requested for pending-word buffers.

This dataset supports future checks; it does not mean that compatibility audits,
bulk migration, or complete existing-note coverage already exist. The current
[field auditor](../../tools/audit_note_contracts.py) checks `en_word` syntax only,
without consulting Diki HTML. Existing unit tests use controlled fixtures/fakes;
the owner's reuse goal does not require making all tests depend on their live
personal cache or Anki collection.

See [Diki compatibility](../contracts/diki.md) and the
[contract-first cleanup discussion](../roadmap.md#future-discussion-contract-first-cleanup-of-older-notes).

## Current behavior and evidence

Result validation now recognizes full collocations and reverse-only results as
valid source HTML without treating them as English→Polish entries. Spelling,
related-entry, and ambiguous-headword choices remain distinct; unknown layouts
produce durable diagnostics. See [Diki result recognition](diki-results.md).

| Area | Inspected behavior | Evidence |
| --- | --- | --- |
| Shared storage | App and CLI use raw HTML/MP3 resources with SQLite metadata; successful resources are shared across request profiles | `external_apis/diki_resources.py` |
| Local reuse | Cache hits are integrity-checked; raw HTML is reparsed locally | `DikiResources._read_cached`, `external_apis/diki_api.py` |
| Provenance | Metadata includes source URL, download time, content digest, and size | `DikiResources._save_locked` |
| Fetch profiles | Interactive and background fetching have separate request state while sharing successful resources | `DikiResources` |
| Current prefetch input | Discovers `.txt` lists, including books, from the configured words directory; does not query Anki for existing vocabulary | `tools/diki_prefetch.py`, `external_apis/diki_lists.py` |
| Preparation | Bounded/resumable batches download HTML and then an advertised recording for exact matches | `tools/diki_prefetch.py` |
| Scheduling | A launchd generator configures background runs independently of the UI | `tools/diki_launchd.py` |
| Reporting | The dashboard measures local list coverage without fetching Diki content | `external_apis/diki_lists.py`, `frontend/src/OfflineDownloads.tsx` |
| Offline mode | `DIKI_OFFLINE=1` prevents Diki fetching, including on missing resources | `DikiResources`, README |
| Freshness | No automatic expiry; explicit successful refresh replaces the current resource for that key, rather than keeping a version history | `DikiResources.path`, `_save_locked`, prefetch `--refresh` |

The launchd configuration and historical installation notes are not proof that a
particular job is currently installed/running. Operational commands and exact
retry/pacing details remain in the [README](../../README.md#diki-offline-html-i-mp3).
`plan.md` / `research.md` retain implementation history; some early decisions were
superseded by later fetching changes.

## Preparation priority: a buffer, then existing notes

The owner typically adds roughly 20–50 words in a week, sometimes less often.
Processing 200 words within a few days is unusual. The priority is therefore to
prepare a useful offline buffer rather than finish downloading every pending
word before serving the existing-note dataset goal.

Intended order:

1. Prepare the first **100 nonempty pending entries of each vocabulary file**,
   including all discovered book sources, selecting before deduplication.
2. Give those HTML/audio goals priority over existing-note HTML-only work.
3. Use remaining eligible work for missing HTML in the one-time inventory.

The owner fixed the window at 100 per file on 2026-11-23, refining the earlier
illustrative target. Duplicates share resources but occupy source positions;
failures do not cause downloading beyond the window. Main/source order is retained
within submissions. Already-running remote requests finish normally; eligibility
still respects retries and global cooldowns. The window is not a daily limit or
throughput promise.

## Source policy: keep the accumulated snapshot

### Query casing and resolved-headword reuse

As of 2026-11-21, request and cache keys preserve casing: `Polish` and `polish`
must not overwrite each other's resources. Lowercase cache paths remain valid.
An unambiguous non-case-distinct lowercase snapshot can seed a capitalized key
without a network request. Resolved aliases seed missing canonical-headword
HTML/audio so a prepared `lead astray` can be saved as `lead somebody astray`
offline. Existing canonical snapshots are retained.

Audio reuse checks the stored source URL against recordings advertised for the
selected headword. Old negative audio discovery is reconsidered under version 2;
old no-exact-match HTML is reinterpreted locally for prefetch/readiness. Download
planning preserves case-distinct list entries. See
[ADR 0005](../decisions/0005-diki-headwords-and-case.md).

### Retention

Downloaded successful resources should be retained and reused. Routine expiry,
periodic replacement, or re-downloading existing content for each check has no
value for the owner's current goal and adds substantial work/download volume.

The accepted dataset is a **rolling Diki snapshot**: pages accumulated over weeks,
not a synchronized capture of the whole dictionary on one date. Compatibility
checks refer to this saved source material. Current online freshness is not a
requirement for each check.

The owner accepts that Diki can change wording or page structure. If assertions
or tests expose a discrepancy, they will manually investigate whether it comes
from code or changed source content. Do not automatically re-download pages,
rewrite expected results, or modify notes simply to make an assertion pass.

Explicit refresh exists as a tool, but is not routine maintenance. This retention
policy concerns already downloaded content; it does not require treating failed
or missing downloads as successes or disabling their existing retry behavior.

See [ADR 0003: Retain a rolling Diki snapshot](../decisions/0003-rolling-diki-snapshot.md).

## Existing-note inventory and current rollout boundary

Explicit `tools.diki_remote export-coverage` reads the normal English vocabulary
types once, excluding Diki-missing/image-only types, and retains a word inventory
under the data root. Startup uses that file and existing cache coverage; it never
scans Anki. Invalid exported English values are reported, not silently rewritten.
The remote scheduler's two priorities implement the intended buffer/backlog split.

Implementation is not evidence that the owner's entire collection is covered:
the updated worker must be deployed, the explicit inventory created, and missing
HTML downloaded/imported over time. The standalone local prefetch remains list-
driven. See [remote preparation](remote-downloads.md) for lifecycle, commands, and
the distinction between verified manual deployment and new scheduling rollout.

## Authority and verification

The primary purposes were explained in batch 12 and priority/snapshot policy in
batch 13 on 2026-11-17. Mechanisms were inspected in code/documentation. These
batches did not trigger downloads, cache refreshes, Anki writes, or jobs. Earlier
isolated resource tests were run for the deck-preservation correction; this was
not a new live cache-coverage audit.
