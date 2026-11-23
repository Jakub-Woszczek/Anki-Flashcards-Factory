# Diki implementation plans

## Approved: automatic remote preparation — 2026-11-23

**Status: implemented and verified locally, with immediate background import and ACK.**
The owner rejected exit-time import and deliberately deferred ACKs. Download each
batch into the existing journal, validate, merge immediately under short cache
locks, verify, and ACK immediately. Shutdown only signals cancellation; ordinary
interruption recovery handles incomplete downloads/imports/ACKs at next launch.
This amendment supersedes deferred-import details in the original research.

### Approach and agreed behavior

See [the scheduling research](research.md#remote-scheduling-research--2026-11-23).
Retain the tested remote fetcher, its pacing/budgets, raw resources, manual CLI,
and acknowledgement-before-deletion safeguards. Add these layers:

```text
one-time normal-note export --> existing-note inventory --> missing HTML ------+
                                                                            |
first 100 entries per source --> missing HTML/audio --> buffer-priority jobs --+--> node
            ^                                                               |
            | successful source advancement                                  v
            +--- background reconcile                       immutable ready batches
                                                                            |
startup: background journal recovery -> one ready-work snapshot ---------------+
                                      -> download -> immediate import -> ACK
shutdown: stop scheduling; do not wait for network work
```

**Activation:** run automatically with the app when both existing remote URL/token
settings are configured. Without remote configuration the app keeps its current
local behavior. Partially configured/unsupported remote setup becomes a visible
background-preparation status error, not a failed save or blocked app startup.
`DIKI_OFFLINE` continues to prohibit local Diki fetching; it does not prohibit
transfers from the configured remote worker.

### 1. Exact entry windows and resource planning

**Files:** `external_apis/diki_lists.py`, `external_apis/diki_remote.py`,
`backend/settings.py`.

- Select the first 100 **nonempty source occurrences before deduplication**,
  matching `SessionStore._entries`. Preserve source order, BOM handling, meaningful
  case, invalid-entry diagnostics, and existing path confinement. Keep default
  full-list discovery/reporting compatible for manual tools.
- Deduplicate work across windows, keeping the main-file-first traversal already
  provided by source discovery. Do not expand past entry 100 to compensate for
  duplicates, missing entries, or download failures.
- Compute missing resource goals from integrity-checked local resources, completed
  staged work, and accepted remote submissions. Buffer goals include recordings
  when available; coverage goals include HTML only. HTML is never uploaded.
- Reuse the current resource planner, cache locks, and no-audio discovery. Short
  local metadata/cache writes during the session are acceptable; HTTP never holds
  the cache lock.
- Do not persist a second authoritative vocabulary queue locally. Keep only
  server-origin-scoped submission/transfer receipts, reconciliation status, and
  interrupted-notification state. Re-read source files on startup and advancement.
- Previously submitted jobs are retained; source edits do not silently delete
  remote work or successful cached source.

Illustrative interface:

```python
windows = discover_lists(entry_limit=100)
goals = plan_preparation(windows, coverage_words, cache_view, staged_view)
# Each goal carries a word, resource requirement, and buffer/coverage priority.
```

### 2. One-time existing-note inventory

**Files:** new `external_apis/diki_inventory.py`, `tools/diki_remote.py`,
`backend/settings.py`; reuse `backend/note_contracts.py` without changing its rules.

- Add an explicit `export-coverage` CLI operation, using bounded read-only
  AnkiConnect queries and the documented two normal note types. Their type scope
  excludes the `Diki_missing` note type and image-only `TEMP Image recall`; do not
  introduce another deck picker or rely on historical deck labels.
- Export English `en_word` values with original casing, deduplicating downloads
  without changing notes. Verify actual returned note type/IDs and field syntax;
  report invalid/missing fields explicitly so incomplete coverage is visible.
- Save the word file and bounded export provenance/report atomically beneath
  `ANKI_FACTORY_DATA_DIR/diki_cache/coverage/`, outside consuming source files.
  A supplied word file can also be loaded explicitly through the CLI.
- On normal application startup, read this inventory without querying Anki.
  Enqueue only missing HTML at coverage priority. The inventory is a one-time
  input, not a recurring collection audit, migration, or audio backlog.
- Preserve existing cache hits and staged/remote coverage. Normal new notes already
  pass through the recurring buffers; the export is not regenerated after saves.

### 3. Persistent server priorities and compatible goal upgrades

**Files:** `deploy/northflank/config.py`, `app.py`, `service.py`.

- Add schema fields with safe defaults/migrations for buffer versus coverage
  priority and resource demand. Existing/manual jobs retain their current default
  resource behavior and become ordinary buffer-priority jobs.
- Select eligible queued buffer jobs before eligible coverage jobs, FIFO within
  the priority class. Already-running HTTP work is not interrupted. Per-resource
  retry delays and global cooldowns still apply; eligible coverage may run while
  a failed buffer word waits for retry.
- Coalesce the same word across both classes, promote queued coverage work when
  it enters a buffer, and upgrade a missing audio goal without fetching HTML again
  when source HTML is already available locally/staged.
- Handle promotions during an in-flight HTML fetch using current persisted demand,
  not only the stale job snapshot read before HTTP.
- Keep issued manifests immutable. If an HTML-only ready/batched/delivered
  generation later needs audio, record an additional goal/follow-up generation
  rather than rewriting that manifest or treating the word as permanently done.
  Existing completed resource receipts prevent repeated HTML downloads. Preserve
  old-ACK isolation and clean old payloads before a newer generation can reuse a
  word's cache paths.
- Do not turn scheduling into automatic retries of terminal failed jobs or
  automatic re-download after lost cache. Preserve explicit recovery flags and
  the daily budgets, request reservation, five-failure ceiling, storage cap,
  single-worker locking, and source retention rules.
- Advertise scheduling/finite-drain capabilities separately from unchanged
  version-1/2 artifact manifests. Old clients/manual calls stay supported; new
  scheduling checks capabilities before relying on new endpoints.

Selection shape:

```sql
SELECT * FROM remote_jobs
WHERE state = 'queued' AND retry_at <= ?
ORDER BY priority, created_at, rowid LIMIT 1;
```

### 4. Finite startup drain with immediate import and acknowledgement

**Files:** `deploy/northflank/app.py`, `service.py`,
`external_apis/diki_remote.py`, `external_apis/diki_transfer.py` if needed.

- Add an authenticated ready-work snapshot operation. Persist the finite set of
  ready job generations (including existing unACKed manifests) at snapshot time.
  Fetching that snapshot must not initiate Diki requests.
- Filter normal manifest enumeration by the snapshot, importing and ACKing each
  batch before requesting the next. There is no need to expose multiple unACKed
  batches. Keep existing size, URL, artifact, and authentication limits.
- Jobs completing after the snapshot wait until a later app launch. A network
  interruption leaves durable snapshot/cursor and artifact journals for recovery;
  do not create a polling loop that waits for more ready words.
- Reuse the tested client transfer implementation with cancellation and a finite
  drain selector:

```python
drain_startup_snapshot(...)   # download -> validate -> import -> verify -> ACK
```

- Keep manual `pull` as the same composition of stage/import/ACK, preserving its tested
  immediate-import behavior and existing interrupted-pull journal compatibility.
- Publish a completed-batch marker only after all artifacts and audio-only source
  context are validated and durable. Incomplete batches are never imported.
- Retain staged artifacts and receipts until the server confirms ACK. A lost ACK
  response must remain recoverable without re-fetching deleted server payloads.
- Revalidate before ACK. If a valid independent local snapshot appeared during the
  session, preserve it, retain the staged bytes until reconciliation is durable,
  and explicitly record the keep-local outcome. Never claim two differing digests
  are identical. Incompatible audio-only context stays unresolved without ACK.

### 5. Background coordinator and lifecycle hooks

**Files:** new `backend/remote_preparation.py`, `backend/app.py`,
`backend/services.py`; small additions to offline coverage/status UI if needed.

- Instantiate an optional application-scoped coordinator from FastAPI lifespan;
  do not start threads or contact a remote service at module import.
- In background at startup, recover interrupted transfers, open one new finite
  drain, and immediately import/ACK its results.
  Reconcile/submit current buffer windows and coverage inventory in background,
  with a separate/coalesced submission worker so a long download cannot stall
  replenishment or the browser.
- Give each worker its own HTTP client. Use cancellable/bounded requests, brief
  local journal locks, and the existing cache lock only for actual local import.
  Do not hold a cache or source lock over HTTP, sleeps, or network-thread joins.
- Notify after successful `_complete_source` and discard consumption. Include
  successful retry-removal/custom-card paths through that common hook. Unresolved
  entries, stale requests, failed saves, and failed source removals do not advance
  the preparation window. Review-only saves have no source-window event.
- At shutdown, stop new work without joining network waits. Leave interrupted
  journals and unsent submissions for startup recovery. Preserve the existing
  Anki synchronization behavior separately.
- Expose local-only preparation state/progress and actionable errors through the
  existing offline panel/status path. Dashboard refreshes must not poll Northflank
  or Anki. Clear remote credentials in the guarded test runner so a developer's
  configured `.env` cannot activate real background work in tests.

### Detailed implementation checklist

- [x] Add exact 100-occurrence window discovery and shared resource-goal planning.
- [x] Add centralized inventory path and durable origin-scoped goal receipts;
      reuse existing cache-root staging and locks.
- [x] Add one-time export/file-import CLI and HTML-only coverage planning.
- [x] Migrate server priorities, demand records, and resource-aware promotions.
- [x] Protect immutable ready transfers and old ACKs across audio follow-ups.
- [x] Add finite ready snapshot filtering to existing bounded transfer enumeration.
- [x] Reuse immediate transfer/import/ACK with cancellation and cache reconciliation.
- [x] Preserve manual submit/status/pull and legacy journal/manifest recovery.
- [x] Add application coordinator, independent submission and drain work, and
      local-only status/error reporting.
- [x] Wire exact successful source-advance notifications and app lifetime hooks.
- [x] Add failure/restart/concurrency/migration regressions described below.
- [x] Update relevant feature pages, contracts/ADR, README, storage layout, and
      deployment guide; mark implemented versus operationally enabled separately.
- [x] Run the full project check and review the diff against the agreed behavior.

Verification: full checks passed with 61 Python files, zero Pyright errors/warnings,
276 tests (270 passed, 6 skipped), and frontend build. The Linux/amd64 worker image
also built and passed a network-isolated, empty-queue scheduling API startup smoke
test under 256 MiB. No real Anki/Diki request, inventory export, remote workload
change, commit, or push was used for implementation verification. See the current
feature/ADR for the implemented contracts; the research preserves earlier proposals.

### Verification strategy

All routine verification uses temporary data, fake Anki, fake clocks/upstream
transports, and the existing in-process client/server HTTP adapter. No live
collection export, app launch against personal credentials, Diki request, cloud
update, commit, or push is part of implementation verification.

Required behavioral cases:

1. First-100 selection before deduplication; duplicates/case variants/invalid lines,
   books, shared words, short files, BOMs, and no out-of-root traversal or queue edits.
2. Partial existing-note coverage; HTML-only requests; exclusion of missing/image-
   only types; malformed note reporting; no Anki scan during app startup.
3. Priority over an existing coverage backlog, retry eligibility, promotion during
   a blocked fake HTTP call, and follow-up audio for already ready/delivered HTML.
4. Import/ACK more than 10 words through a finite drain; resume across failure;
   exclude jobs that finish after the snapshot; bound manifests and response sizes.
5. Imports use short cache locks; requests never hold cache/source locks;
   slow/offline remote work does not delay saves, advancement, or shutdown.
6. Successful save/discard/custom/retry-removal events replenish once; failed or
   stale source operations and review-only saves do not. Startup catches edits and
   notifications lost to a process interruption.
7. Shutdown does not wait for network work or initiate remote calls. Startup
   recovers imported-but-unACKed batches, partial staging, lost ACKs, corrupt files,
   changed audio-only HTML, concurrent local snapshots, and terminated workers.
8. Old schema/data/receipts survive migration; manual CLI tests continue to pass;
   old server capabilities fail clearly without fallback that changes semantics.

Run focused tests/Pyright while implementing; finish with
`.ankiFac/bin/python -m tools.check` and `git diff --check`. Existing explicit
loopback transport checks are needed only if that transport code changes.

### Rollout and rollback

- New scheduling requires an updated worker and Mac client. Capability detection
  keeps the current deployed worker usable for manual commands until the owner
  chooses to publish/redeploy the changes.
- Preserve the entire remote `/data` volume and local durable staging/inventory.
  Additive migrations retain existing jobs, receipts, manifests, and budgets.
  Do not erase queue state or automatically retry terminal failures on upgrade.
- Disable automatic scheduling by removing remote configuration from the app's
  environment when troubleshooting; retained staged/ACK state remains recoverable.
- Roll back code without deleting durable source/cache data. Do not run old
  lifecycle code over newly staged work expecting it to process new state formats;
  retain compatible manual tooling until those journals are resolved.

### Open decisions

No further product questions. The owner approved implementation with immediate
background import and ACK; preserve the rest of the reviewed plan.

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
