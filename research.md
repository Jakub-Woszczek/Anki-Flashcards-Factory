# Offline Diki research

## Remote scheduling research — 2026-11-23

**Subsequent owner correction:** merge downloaded batches into cache and ACK
immediately in the background. No exit-time import or intentionally deferred ACK.
Existing cache locks are sufficient for the personal workflow. The implementation
plan incorporates this correction; deferred-import analysis below is historical.

Status: source inspection complete; implementation now authorized. This section
records findings for the owner's requested scheduling change. Earlier sections
below remain historical evidence, not current path/configuration instructions.
Source line references below describe the pre-scheduling `089a609` implementation;
the approved implementation and verification are recorded in the feature/ADR.

### Owner-confirmed scheduling requirements

- Prepare the first **100 pending nonempty entries per source file**, in file
  order, including advertised audio where possible. Duplicates consume positions
  in that window but share downloads. Failed downloads do not extend the window.
- Replenish asynchronously after a source entry is resolved and processing moves
  on; reconcile at startup for external edits and interrupted submissions.
- Give recurring preparation priority over a one-time existing-note HTML backlog.
  Existing-note input is an exported English-word file, not a repeated Anki scan.
- Existing-note coverage fills only missing HTML. Retained HTML already provides
  part of that coverage; there is no routine refresh. Existing-note audio is not
  part of this backlog.
- The owner clarified that `Diki_missing` is the unrelated deck, with its own
  note type. The existing documented normal-note scope is
  `Basic [reverse+audio]` and `Basic [reverse+audio+image]`; the missing type and
  `TEMP Image recall` are excluded from field-contract work. There is no request
  for a new deck picker or content migration.
- At application launch, perform one background drain of completed remote work
  to durable local staging, while the owner uses already cached vocabulary.
- At normal application exit, import completed staged work into the shared cache
  locally. Do not wait for remote network operations. Recover completed staged
  work at the next startup after an interrupted session.

### Current data flow and boundaries

```text
source .txt files --discover_lists--> manual submit --HTTPS--> one FIFO remote queue
                                                             |
                                                             v
                                                       Diki HTML / MP3
                                                             |
                                                             v
manual pull <--- oldest unACKed manifest <--- complete remote resources
    |
    +--> staged files --> shared cache import --> cache re-read --> remote ACK
                                                                    |
                                                                    v
                                                         receipt, payload deletion
```

1. **Sources and window semantics.** `external_apis/diki_lists.py:18-48` reads all
   text lists, main file first and other paths alphabetically, then deduplicates
   words. Taking `source.words[:100]` would therefore be incorrect for the new
   requirement. The window must be selected before deduplication, using the same
   nonempty-entry definition as `backend/storage.py:146-160`. Preserve meaningful
   case through `external_apis.diki_resources.normalize_word`, not the lowercasing
   helper in `backend/word_list.py:10-11`. Existing file confinement and UTF-8 BOM
   handling also apply. Source files remain authoritative and must not be edited
   by download preparation.
2. **Source advancement.** `backend/services.py:773-797` funnels successful
   creates, updates, custom cards, and removal retries through `_complete_source`.
   Discard separately calls `complete_current` at `:867-870`. A save whose source
   removal fails must not advance the window. `backend/storage.py:346-412` already
   provides exact-entry consumption and durable replay. A scheduler notification
   should occur only after successful local consumption and should merely signal
   background work; no HTTP call belongs inside source locks or save requests.
3. **Application lifetime.** `backend/app.py:33-42` provides a FastAPI lifespan;
   `:70-88` implements the explicit browser shutdown route. `main.py:30-34` attaches
   the Uvicorn server used by that route. Start scheduling from lifespan rather
   than module import or every workspace open. Preserve the independent existing
   Anki sync flow; "no network at exit" here concerns remote dictionary work.
4. **Local command behavior.** `tools/diki_remote.py:13-65` implements manual
   submit/status/pull, with offline-only local resources. Bare submit currently
   scans complete source files. `external_apis/diki_remote.py:130-203` computes
   HTML/audio work from the local cache, never uploads HTML, and batches compact
   instructions. A scheduled HTML-only coverage mode must be explicit; the
   existing submit default requests audio for uncached resolved entries.
5. **The present transfer is inseparable.** `_transfer` in
   `external_apis/diki_remote.py:298-350` stages, imports, verifies, ACKs, then removes
   its journal. `pull` at `:352-401` recovers such journals and immediately performs
   the same sequence. This code cannot be used unchanged for startup staging.
6. **Only one unACKed batch is exposed.**
   `deploy/northflank/service.py:449-497` first returns the oldest unacknowledged
   manifest, unchanged, before building a new one. Limits are 10 words, 32 MiB
   payload, and 512 KiB manifest (`external_apis/diki_transfer.py:20-26`). Delaying
   ACK without changing enumeration would restrict staging to one batch. A finite
   ready-work snapshot with bounded pagination is needed; a single startup drain
   must not chase jobs that finish after its initial snapshot or turn into polling.
7. **Server queue and resource goals.** Remote jobs are unique by case-preserving
   word. `DownloadService.submit` (`service.py:208-279`) skips every known word
   unless explicit recovery flags apply. `run_cycle` (`:315-447`) chooses eligible
   jobs by `created_at,rowid`, with no priority. Merely submitting buffer jobs
   first does not prioritize them over an already queued coverage inventory.
   Merely skipping known words also cannot upgrade an HTML-only coverage request
   when that word later enters a buffer and needs audio.
8. **Immutable outbox and generations.** `_ready` (`service.py:294-313`) stores
   artifact metadata; `next_transfer` freezes it into a checksummed envelope.
   `acknowledge` (`:526-543`) commits delivery before `_cleanup_delivered` deletes
   word payloads. An upgrade must not mutate an issued manifest or allow an old
   ACK to delete a newer generation's files. Priority promotion, missing-audio
   follow-up work, and simultaneous coverage/buffer demand need explicit tests.
9. **Retention and imports.** Local `_import` (`diki_remote.py:278-296`) currently
   saves every transferred artifact, including replacing a valid cache file that
   may have appeared since submission. Automatic deferred import must instead
   preserve valid independent local snapshots, while repairing missing/corrupt
   files and checking audio against the actual retained HTML. If preserved local
   content differs from a manifest, retain the validated staged copy and record
   the reconciliation outcome before ACK; do not silently change dictionary
   source identity or falsely claim that manifest bytes match a different cache.
10. **Paths and credentials.** `backend/settings.py:24-69` owns all data paths.
    Existing staging is under `diki_cache/remote-imports/<origin-hash>/<batch-id>`.
    Keep durable staging and coverage inventory under the data root and outside
    `words_to_add/` so source discovery cannot consume the coverage file. Reuse
    HTTPS validation, constant-time token authentication, bounded bodies, URL
    allow-lists, SHA-256, and fsynced writes. Store no credential in journals/status.
11. **Export scope.** `tools/audit_note_contracts.py:30-58` demonstrates exact
    note-type searches, bounded `notesInfo` reads, actual model verification, and
    strict `en_word` parsing. Reuse these boundaries for an explicit one-time
    export. Report malformed/missing English fields; do not rewrite them or count
    them as covered. Normal startup reads the exported file and does not query
    the collection. The export is not a compatibility audit or note mutation.
12. **Tests and current work.** `tests/test_diki_remote.py:40-118` already provides
    an in-process HTTP adapter and fake upstream clock/transport; reuse those for
    priority and split-transfer regression tests. `tools.test_offline` blocks all
    sockets/DNS and disables loopback/live opt-ins. Existing edited deployment
    and feature docs contain earlier container verification and must be preserved.

### Required state transitions

```text
remote ready -> locally staging -> validated/staged (no shared-cache import, no ACK)
              -> local import/reconciliation -> durable pending ACK
              -> next-start remote ACK -> server cleanup -> local journal cleanup
```

Pending ACKs must be revalidated/reconciled before sending, including after a lost
ACK response or an offline startup. Completed staging survives a crash; incomplete
artifacts are never published as importable. Startup should acknowledge previous
durable imports before taking its one new ready-work snapshot. Shutdown signals
cancellation, imports only completed batches, and never joins a network wait.
Use small local critical sections to prevent a late background writer publishing
an importable batch halfway through shutdown's snapshot.

### Research outcome

No further product interview is needed. The implementation requires coordinated
server/client evolution, rather than only a scheduler around the old `pull`.
Keep manual commands and protocol-1/2 payload validation compatible; expose a
separate scheduling capability so an old deployed server produces a clear status
message, never silent fallback to immediate imports or unbounded submissions.
Detailed implementation and migration/testing work belongs in the new draft
section of `plan.md`, for review before code changes.

## Data-repository separation research — 2026-11-22

Approved for implementation after the owner reviewed the migration plan in chat.
The owner also approved deleting the two deprecated `external_apis/tmp/` MP3s.

- `backend/settings.py:12-34` resolves the database and main queue inside the code
  checkout. `tools/diki_lookup.py:22` independently hard-codes the queue.
- `external_apis/diki_resources.py:114-115` and `diki_lists.py:19-21` independently
  resolve cache/list environment overrides. This can split browser and prefetch data.
- `backend/storage.py:385-403` and `word_completion.py:314-324` store absolute
  archive references. Source workspace names and save-entry associations are relative.
- The active database contains 11 consumed source receipts and no prepared receipts;
  copying an unfinished removal would require special care because recovery also
  checks filesystem identity. Recheck before migration and refuse unfinished removal.
- Durable inventory: two queues; 1,037 cached HTML files; 437 cached MP3s; application
  and cache SQLite databases; 14 archive files; root `Backup.apkg`. Logs, generated
  plists, locks, and relay credentials are local-only. Fixture HTML stays with code.
- The installed launchd plist references a missing previous checkout. No backend or
  prefetch process was found and the launchd service was not loaded at preflight.

```text
code/.env -> ANKI_FACTORY_DATA_DIR -> external data repository
                                     |- queues, SQLite, HTML/MP3, archives/backups
                                     `- ignored logs, runtime files, local credentials
```

Use lazy centralized paths, one required root, stable relative source identities,
relative archive references, consistent entry-point dotenv loading, and isolated
temporary test roots. SHA-256 verifies copies; no credentials enter version control
and no network transport/certificate behavior changes. Current contracts/ADRs remain
authoritative over the historical research below.

## Q-001 research — 2026-11-21

The sections below retain historical offline-cache research. Current queue findings:

- `backend/storage.py:62-86` copies incoming words to `session_queue`;
  `get_session` and `complete_current` subsequently operate on that copy.
- `backend/app.py:99-110` accepts pasted/uploaded content or snapshots the main file.
- `backend/services.py:678-719` saves through `WordCompletion` then advances the
  independent session queue. Skip and keep-existing share that advancement path.
- `backend/word_completion.py:239-295` archives/removes every normalized match in
  the main file, even when a save originated in a book or tag/flag review.
- `backend/word_list.py` already provides cooperating-writer locks, atomic replacement,
  and CLI append. Reuse those primitives; preserve original bytes when consuming.
- Browser uploads do not identify an editable original path. The owner retired
  uploads, pasted queues, queue editing/diffs, and duplicate-note deletion instead.
- Read-only SQLite/file comparison found one main add queue (394 entries), no import
  add queues, and 25 queue entries absent from the main file. Owner approved appending
  those entries in queue order before retiring the snapshot.

```text
Before: source file -> SQLite word snapshot -> UI -> main-file word matching
After:  source file <-> current-entry reference -> UI -> exact source consumption
                         |                         |
                    settings/draft          save + removal receipts
```

Only a current-entry fingerprint/reference is needed in SQLite, not another pending
word list. Mutations need client entry IDs, cross-process serialization, append-aware
file validation, and durable before/after removal receipts. Ambiguous external edits
must preserve the file. Offline tests must cover crash boundaries and identical lines.

Implementation review: resolved source paths are confined to the source directory,
SQL values use parameters, and SHA-256 fingerprints detect content changes. The
feature needs no credentials or certificate handling. Existing credential/service
configuration is reused rather than embedded in queue code. Entry identity is
revalidated after dictionary/audio preparation as well as before file consumption;
an external edit during lookup cannot attach the old draft to a new source entry.

## Original flow before offline caching

`backend/services.py:317` calls `DikiApi.get_translations`, then
`possible_spellings` on an empty result. Both methods independently request the
same HTML (`external_APIs/dikiApi.py:31,184`). Pure BeautifulSoup parsing already
exists in `parse_meanings` and `parse_translations` and can be reused unchanged.
Diki's 404 responses can contain valid spelling suggestions.

`DikiApi.diki_audio_harness` guesses six pronunciation URLs and writes directly
to an Anki media directory, ignoring existing files. `FactoryService._write_audio`
then reads that file and sends it to AnkiConnect's active collection. Failed audio
currently clears the mapped sound field even on updates.

Word-list imports use one fixed file (`backend/settings.py:34`); other text files
are manually imported in the browser. Session queues delete completed rows and
are therefore unsuitable as the source for original-list download coverage.
SQLite is already used for local application data; `data/` is gitignored.

```text
Original: UI -> FactoryService -> DikiApi -> requests -> parser
Implemented: UI / CLI -> DikiApi -> shared disk resources -> paced requests
                                     |
                         HTML + MP3 + SQLite metadata
```

## Integration and verification

Keep parsing independent of storage. Use a separate cache database, independent
of Anki and session initialization. Discover original text files for coverage,
deduplicating normalized words without editing lists. All HTTP requests must use
the same cross-process pacing lock, including audio fallback attempts.

Existing parser regression fixtures are safe offline. Some legacy Diki tests use
live HTTP, and AnkiConnect tests can mutate real notes, so verification must use
explicit mock-backed test selections. Frontend validation is `npm run build`.

Offline means internet-independent Diki lookup/export with local Anki running;
Gemini and AnkiWeb sync still require internet.

## Live transport investigation (2026-11-08)

Reproduced the old GET from `git show HEAD:external_APIs/dikiApi.py`, including
the original Mozilla User-Agent, outside the app with isolated temporary output.
It also times out before receiving HTTP headers. Restoring the header is correct
compatibility behavior, but it does not by itself fix this live failure.

Controlled requests were spaced 15–25 seconds apart with the launch agent paused.
Findings:

- DNS and TLS work; an unrelated HTTPS control request returned 200 in 0.15s.
- Ordinary requests and curl (HTTP/1.1 and HTTP/2) stall on dictionary pages.
- The homepage and direct `take.mp3` returned 200 in some probes; the MP3 was
  10,820 bytes. Other homepage attempts stalled too.
- Two isolated Chrome probes obtained real `take` HTML with 28 exact meanings,
  but later Chrome probes stalled as well. Browser impersonation and retaining
  a temporary browser profile did not produce a reliable fix. No browser client
  or dependency was retained in the application.
- Crucially, normal requests with the ORIGINAL headers and a 130-second read
  timeout received HTTP **524** after approximately **125 seconds** for both
  `take` and `bind`. This identifies a Cloudflare-to-Diki origin timeout; it is
  not an exception caused by BeautifulSoup, SQLite, disk writes or launchd.
  The underlying reason for Diki's origin not responding is not established.

Separate implementation defects found and corrected:

1. Restore the original User-Agent instead of changing transport identity while
   adding caching.
2. A real dictionary page includes `challenge-platform` JS detection markup.
   That script alone must not cause valid dictionary HTML to be classified as
   an anti-bot challenge.
3. Retain the actual request exception in error metadata and reports.
4. Do not end an entire batch on one word's read timeout/server error. Continue
   to other words, with a circuit breaker after three consecutive failures.
5. Persist in-progress attempt/HTML counts before waiting on audio.

The origin errors blocked live verification during this investigation. Later,
after Diki recovered, ordinary requests returned real dictionary HTML in 0.48s
and the scheduled job populated the cache. By November 9 it had downloaded 85
HTML pages and 70 MP3s, with 70 words fully available offline. A later anti-bot
challenge triggered the expected cooldown. No browser transport was needed.
