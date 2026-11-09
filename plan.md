# Approved implementation plan: offline Diki

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
