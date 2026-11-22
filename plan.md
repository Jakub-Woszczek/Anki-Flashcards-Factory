# Approved implementation plan: offline Diki

## Approved data-repository split — 2026-11-22

The owner approved the researched chat plan, all durable data in the data repo,
required `ANKI_FACTORY_DATA_DIR`, Git-versioned HTML/MP3 snapshots, deletion of the
two deprecated temporary recordings, and implementation/documentation now.

- [x] Centralize lazy paths in `backend/settings.py`; load code-local `.env` at
  entry points. Replace per-component path environment settings, preserve explicit
  test/CLI overrides, and keep code/build/test-fixture paths code-local.
- [x] Update browser stores, resource/list providers, capture/prefetch/cleanup,
  relative archive references, launchd paths, and frontend guidance.
- [x] Add an explicit offline migration tool: no destination overwrite, consistent
  SQLite snapshots, pending-operation preflight, SHA-256 manifest, relative active
  backup references, source retirement only after destination validation.
- [x] Migrate current queue bytes and durable files, update local `.env`, delete
  deprecated MP3s, and regenerate/install the scheduler without a live download.
- [x] Document the implemented layout, data Git policy, migration evidence, and ADR.
- [x] Verify relocation and consumer agreement with temporary stores/fake transports,
  run `python -m tools.check`, and verify both Git worktrees and migration hashes.

Rollback uses the manifest's copied-file mapping and retained original SQLite snapshot;
account for post-cutover writes before restoring. No Anki collection operation or
live Diki verification is part of this work. The data repository is a directory
dependency, not a submodule or runtime Git integration.

Completed: full quality check passed (47 formatted Python files, zero Pyright
errors/warnings, 163 tests with 2 live checks skipped, frontend TypeScript/build).
Migration verified 1,497 files/snapshots and all cached resource digests/sizes;
data Git index includes durable HTML/MP3 and excludes local credentials/runtime files.
Detailed evidence lives in `docs/features/data-storage.md`.

## Approved Q-001 implementation — 2026-11-21

Owner approved implementation after refining the plan in conversation. Historical
offline work below remains unchanged.

- [x] Replace `SessionStore` word snapshots with discovered project `.txt` sources;
  reuse existing main-file target settings, retire migrated snapshot rows, and retain
  only current-entry references, drafts, settings, and completion history.
- [x] Add append-aware entry fingerprints, client entry IDs, shared operation/file
  locks, exact-line removal, backups, and idempotent durable removal receipts.
- [x] Separate Anki save verification from interactive source cleanup. Include source
  entry identity in save intents; review saves must not consume word files.
- [x] Replace generic skip/keep-existing with discard. Remove pasted/uploaded queue
  creation, queue editing/diff/deletion, and duplicate Anki-note deletion UI/API.
- [x] Append the 25 approved SQLite-only entries to the main file in snapshot order,
  rechecking absence; migrate the actual local queue without contacting Anki/Diki.
- [x] Add meaningful offline regressions for duplicates, changed lookup spelling,
  books, concurrent appends, stale requests, restart and file-write/SQLite boundaries.
- [x] Update handbook/ADR/README/backlog and run `python -m tools.check`.

Implementation focus: `backend/storage.py`, `backend/word_list.py`,
`backend/services.py`, `backend/word_completion.py`, routes/schemas, and frontend
source/workspace controls. Preserve the owner's existing `TranslationEditor` changes.
Existing `S-001` confirmation semantics and optional `Q-002` draft removal are separate.
Recovery: retain existing schema/history and file backups; do not reconstruct source
files from stale SQLite snapshots. No live collection tests or writes.

Q-001 verification: full check passed on 2026-11-21 (Ruff lint/format, Pyright,
132 offline tests with 2 opt-in live checks skipped, frontend TypeScript/build).
Local migration preserved the main target, retired 394 snapshot rows, and exposed
645 main / 682 Fablehaven entries directly from files. The 25 approved missing
entries were appended and rechecked before migration; database backup retained.

Approved in conversation, including 20 seconds +/- 5 seconds of independently
sampled jitter after each completed request. Implementation is authorized.

## Tasks

- [x] Add `external_APIs/diki_resources.py`: atomic hashed HTML/audio storage,
  SQLite metadata, cache-first and strict offline modes, refresh, persisted retry
  state, one cross-process HTTP request at a time, persisted pacing and cooldown.
- [x] Route Diki HTML and audio through the provider. Retain pure parsers and the
  compatibility audio harness. Upload cached bytes directly to active Anki;
  preserve existing sound fields on failed updates. Surface lookup failures.
- [x] Add shared recursive word-list discovery (main file first) and resumable
  `tools/diki_prefetch.py`: 25 attempted words, 600-second budget, one job lock,
  persisted audio fallback progress, backoff and run summaries.
- [x] Add a launchd plist generator with absolute interpreter/project paths,
  login and 30-minute scheduling, plus install/uninstall instructions.
- [x] Add a disk-only coverage endpoint and home-screen panel showing per-list
  HTML/audio/exact-match readiness, exceptional states, last run and cooldown.
- [x] Add meaningful mocked offline, pacing, retries, resume, coverage and export
  tests; run targeted Python tests and frontend build; document operations.

## Decisions

Cache: `data/diki_cache/{index.sqlite3,html/,audio/}`; no automatic eviction.
Shared words download once. 404 suggestion pages count as HTML, not ready.
No-recording is terminal until explicit refresh; transient failures retry later.
Recognized blocks and HTTP 403/429 stop batches and impose at least six hours of
cooldown (or longer Retry-After). Cache hits never wait on the request lock.
The runtime budget may end before 25 words; missing audio variants resume on the
next run. Dashboard inspection never calls Diki or Anki.

## Verification and rollback

Verify zero-network cache hits, cache-only misses, 404 reuse, invalid/block
responses, persistent randomized pacing, corrupt files, budget interruption,
audio variant resume, list deduplication and cached export. Use fakes for Anki.
Run parser regressions and frontend typecheck/build. No live Anki mutation tests.

Rollback: unload the launch agent, revert feature files, retain the independent
cache directory for later reuse. No existing list/session migration is required.

## Verification results

- `python -m unittest` with the ten documented modules: 50 tests, 48 passed,
  two live HTTP tests skipped by default.
- Frontend `npm run build`: TypeScript and Vite production build passed.
- Generated launchd plist: `plutil -lint` passed.
- Real local coverage report: 1,045 unique main-list entries and 648 unique
  Fablehaven entries; report performed no network requests.
- `git diff --check`: passed.
- Installed the generated agent under `~/Library/LaunchAgents/` and loaded it.
  `launchctl list` confirms the agent and exit status 0. Its first live batch
  encountered a connection failure on `bind`, recorded a retry and cooldown,
  and exited normally. The initial cache was empty; later scheduled runs resumed
  successfully after Diki recovered (see the live verification below).

## Follow-up: live failure investigation

- [x] Compare the old request directly against the cache request in isolated
  temporary directories, using the original header from Git.
- [x] Trace the underlying exception; confirm HTTP 524 from normal requests with
  a longer diagnostic timeout for both `take` and `bind` (about 125 seconds).
- [x] Restore the original header; fix false block detection on normal
  Cloudflare-tagged dictionary HTML; retain detailed request failures.
- [x] Continue after isolated read timeouts/5xx errors, with a three-consecutive-
  failure circuit breaker; retain 20 +/- 5 second spacing and hard-block cooldown.
- [x] Regression checks: 55 tests, 53 passed and two live tests skipped.
- [x] Reloaded launchd and verified a real batch with the corrected code:
  three paced requests, three explicit ReadTimeout reports, circuit breaker,
  normal exit status 0. It remains enabled on the 30-minute schedule.
- [x] Live HTML/audio batches verified after Diki recovered: by November 9 the
  background downloader had cached 85 HTML pages and 70 MP3s, with 70 words fully
  ready offline. It subsequently recognized an anti-bot challenge and honored
  the configured cooldown. Browser experiments were removed; normal requests
  remain the only HTTP transport.
