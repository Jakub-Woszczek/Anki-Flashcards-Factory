# Diki cache and background preparation

Last updated: 2026-11-22.

Specification status: two purposes, bounded queue-buffer priority, and rolling
snapshot retention confirmed. Exact buffer configuration/book selection and the
existing-note population mechanism remain to be designed.

Implementation status: shared raw-HTML/audio caching, list-driven prefetch, strict
offline mode, and coverage reporting exist. The current prefetch entry point
does not discover vocabulary directly from existing Anki notes.

Since 2026-11-22, cache paths are under `ANKI_FACTORY_DATA_DIR/diki_cache/`.
Both HTML and MP3 snapshots, together with `index.sqlite3`, are deliberately
versioned in the separate data repository. Browser/CLI/background defaults now
share centralized paths; independent cache/list environment variables were retired.
See [data storage and migration](data-storage.md). Resource selection, snapshot
retention, and interactive/background request isolation remain unchanged.

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
or contract logic to run against the same local material. HTML is central to this
second goal; the scope/priority of preparing audio for existing notes is not yet
specified.

This dataset supports future checks; it does not mean that compatibility audits,
bulk migration, or complete existing-note coverage already exist. The current
[field auditor](../../tools/audit_note_contracts.py) checks `en_word` syntax only,
without consulting Diki HTML. Existing unit tests use controlled fixtures/fakes;
the owner's reuse goal does not require making all tests depend on their live
personal cache or Anki collection.

See [Diki compatibility](../contracts/diki.md) and the
[contract-first cleanup discussion](../roadmap.md#future-discussion-contract-first-cleanup-of-older-notes).

## Current behavior and evidence

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

1. Prepare the front of the main pending queue first: **roughly 100 words** was
   offered as a safe initial buffer.
2. Prepare a similar front-of-queue buffer for book vocabulary.
3. Once those buffers are covered, work on HTML for older/existing Anki notes.

The number 100 is an illustrative starting target, not a strict daily limit,
immutable constant, or throughput promise. The exact set of book lists and buffer
configuration were not settled. Intake examples explain the rationale; they are
not limits imposed on the owner.

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

## Coverage gap: existing Anki vocabulary

The cache can already reuse resources for any word fetched through its provider.
An existing-note word can be present because it was also in a list or looked up
interactively. However, the current prefetch discovers lists, not the existing
Anki collection, so it does not by itself establish the owner's desired gradual
coverage of existing vocabulary.

The current list-driven ordering also does not implement the intended transition
from bounded queue buffers to existing-note preparation. Record the accepted
priority without silently choosing a collection scan, exported list, profile/model
scope, or scheduling mechanism as its implementation.

## Remaining design details

1. Select the mechanism/scope for obtaining existing-note vocabulary.
2. Define exact buffer configuration and which book queues receive preparation.
3. Clarify resource-readiness details with audio behavior where needed.

These can be refined during implementation planning. The owner has answered the
priority and freshness questions; do not keep reopening them as prerequisites.

## Authority and verification

The primary purposes were explained in batch 12 and priority/snapshot policy in
batch 13 on 2026-11-17. Mechanisms were inspected in code/documentation. These
batches did not trigger downloads, cache refreshes, Anki writes, or jobs. Earlier
isolated resource tests were run for the deck-preservation correction; this was
not a new live cache-coverage audit.
