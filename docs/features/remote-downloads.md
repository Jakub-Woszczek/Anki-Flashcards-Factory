# Remote Diki downloader

Last updated: 2026-11-24. Manual downloads verified live; automatic scheduling
implemented locally and requires an updated worker deployment.

The owner requested restoring the Northflank downloader from stash
`8d5a6b5570d15ae80eb73ea66650c7ab51c0b13e` (index parent `12bc1d6`) while
preserving its behavior. The worker is an optional remote dictionary-preparation
component; the browser, backend, queues, and Anki remain on the Mac.

## Preserved workflow

1. The Mac explicitly submits missing work from text lists or command-line words.
   It neither consumes nor rewrites the source queues.
2. A single resident worker fetches directly from Diki into a durable `/data`
   volume, including SQLite jobs, budgets, retries, and transfer records.
3. Completed work stays remote until the Mac requests it. Manual `pull` remains
   available; the application's automatic startup flow is described below.
4. Pull stages and validates the complete manifest and payloads, imports into the
   shared local cache, then re-reads the imported data before sending an ACK.
5. The server commits delivery before deleting payloads. Stable manifests, local
   journals, and delivery tombstones support interrupted transfers and lost ACKs.

The Mac never uploads cached HTML. If only audio is missing it submits bounded
advertised recording URLs, the local HTML digest, and selector version. Missing
recording links are recorded locally; exhausted remote URLs produce a small
no-audio receipt. Audio-only transfers require the original local HTML.

Default budgets are 400 upstream attempts and 3,600 active work seconds per
UTC day, 180-second slices, 10 words/cycle, 128 MiB pending payloads, 60-second idle
polling, and five failed attempts before explicit retry. Requests use the existing
20±5-second pacing and adaptive cooldowns. Manual retry/redownload flags preserve
global budgets/cooldowns and guard old ACKs against new job generations.

## Integration with the current checkout

- Imports use `external_apis` and `diki_api.py`.
- Mac commands load `backend.settings.load_environment`; local resources and list
  overrides follow the single `ANKI_FACTORY_DATA_DIR` contract.
- Validation uses the current shared result inspector and resolved-headword rules.
  Case-distinct jobs/resources remain separate. Old alias metadata is reinterpreted
  locally rather than forcing a new HTML fetch.
- Imports seed missing local canonical-headword resources. Server-side alias
  seeding is disabled because remote payloads are temporary, job-owned outbox data;
  ACK cleanup must not leave unrequested canonical copies behind.
- Protocol remains version 2; legacy protocol-1 manifests remain readable. The
  current audio discovery version is 2; client/server selector versions must match
  for audio plans and negative results, as required by the original protocol.
- Shared cache writes fsync files and directories and commit SQLite with
  `synchronous=EXTRA`/`fullfsync=ON` before an import can be acknowledged.
- Bearer secrets stay in runtime configuration, HTTPS certificates are verified,
  redirects are refused, source URLs are allow-listed, and artifacts use SHA-256.
  No credential or certificate is embedded in the image.

## Daily request limit — 2026-11-24

At the owner's request, the worker's daily Diki HTTP-attempt default increased
from 100 to **400** in both configuration paths and the deployment environment
example. All attempts, including failures and 404s, count toward this limit.
The separate 3,600-second active-work budget includes pacing waits and can stop
work before 400 attempts are used. Priorities, pacing, cooldowns, and the UTC reset
retain their existing rules.

Existing deployments must set `REMOTE_REQUESTS_PER_DAY=400` if they explicitly
configured the old value, then redeploy and verify `requestLimit: 400` through
remote status. A code push alone does not override a deployed environment value.
See [deployment budgets](../../deploy/northflank/README.md#budgets-and-pacing).

## Automatic scheduling — 2026-11-23

[ADR 0009](../decisions/0009-remote-preparation-scheduling.md) owns the accepted
behavior. With `DIKI_REMOTE_URL` and `DIKI_REMOTE_TOKEN` configured, FastAPI lifespan
starts one application-scoped coordinator. Importing modules or opening another
workspace does not start it again. Missing configuration leaves local behavior
unchanged; partial configuration/unsupported workers are visible in the offline
panel without blocking vocabulary processing.

### Recurring buffers and existing-note coverage

- Select the first **100 nonempty occurrences per source file before deduplication**.
  Shared words download once and meaningful case remains separate. Invalid or
  duplicate occurrences count toward the window; failures do not expand it.
- Submit missing HTML/audio goals in background at startup and after successful
  source removal. Save/update, discard, custom-card completion, and removal retry
  are covered. Failed removal and review-only saves do not advance source windows.
  Notifications coalesce; no HTTP request runs inside source/save locks.
- Explicit `export-coverage` reads normal Anki note types once and saves
  `diki_cache/coverage/inventory.json`. Missing-Diki and image-only types are excluded.
  Invalid/unprocessable English fields are reported; notes are not changed. An
  already prepared word list can be loaded with `coverage --file`. Since
  2026-11-24, the separate [existing-note coverage worker](offline-cache.md#strict-coverage-for-existing-anki-notes)
  also reconciles this export with Anki once per launch, after publishing saved
  statistics. Version 2 retains note IDs/fields/errors alongside the word list.
- The remote scheduler reads that saved file and submits **only missing HTML**,
  reusing partial cache coverage and safe capitalization aliases. Successful
  inventory reconciliation notifies it to reconsider the refreshed word list. The
  inventory is outside `words_to_add/` and cannot become a consuming source queue.
- Eligible buffer jobs precede eligible coverage jobs, FIFO within each class.
  Existing manual jobs default to buffer priority. Running requests, retry delays,
  global cooldowns, daily budgets, storage limits, and failure ceilings remain.
- HTML-only goals can gain audio without another HTML fetch. Frozen manifests
  remain unchanged; follow-up generations preserve old-ACK isolation. Terminal
  failed jobs still require explicit retry.
- Server-origin-scoped accepted-goal receipts in the local cache index avoid
  repeated submissions. They do not replace source files or count remote work as
  locally cached. Existing server receipts still protect against accidental replay
  after volume loss or cache deletion; use the documented explicit recovery flow.

### One startup drain, immediate import

A separate drain worker recovers interrupted journals, snapshots ready job
generations once, then downloads, validates, **immediately imports and ACKs** each
batch before requesting the next. It handles multiple 10-word batches; jobs that
complete after the snapshot wait until another launch. There is no periodic remote
polling during the session. A separate submission worker keeps replenishment
independent of slow downloads.

Automatic imports retain valid independent local snapshots, use short cache locks,
validate audio against retained HTML, and journal reconciliation before ACK.
Incomplete batches never reach cache; interrupted downloads/imports/lost ACKs
recover through durable journals. Changed audio-only source HTML still blocks ACK.

Shutdown signals cancellation without joining network waits, importing an exit
backlog, or intentionally deferring ACKs. The existing Anki sync flow is independent.
The offline panel now emphasizes strict existing-note HTML coverage and its
manual-review list. The routine submission/drain summary was removed at the
owner's request on 2026-11-24; actual errors remain visible. Refreshing it does not
contact Northflank.

Scheduling needs a worker reporting `schedulingVersion: 1`. Additive migrations
preserve jobs, manifests, receipts, and budgets. Protocol-2 artifacts and existing
manual APIs stay supported. Publishing/redeploying code remains an owner operation.

After updating the worker:

```bash
# Optional explicit read-only Anki export. Startup can also create/reconcile it.
# No dictionary fetch or note changes from the export itself.
.ankiFac/bin/python -m tools.diki_remote export-coverage
# Normal launches then reconcile, submit, and drain automatically.
.ankiFac/bin/python main.py --app
```

Bare manual `submit` retains full-list behavior, rather than the automatic 100-entry
windows. Manual `coverage` submits inventory HTML only; manual `pull` retains its
immediate import/ACK behavior.

### Scheduling verification

The separate header health button is documented below; its checks do not run a
scheduler reconciliation or a startup drain.

`.ankiFac/bin/python -m tools.check` passed Ruff lint/format (61 Python files),
Pyright with zero errors/warnings, 276 tests (270 passed, 6 skipped), and frontend
TypeScript/build. Twenty-five new regressions exercise exact occurrence windows,
inventory scope/partial reuse, queued/running/frozen/delivered promotions, old-ACK
isolation, multi-batch finite drains, cancellation/lost-ACK recovery, retained cache
snapshots, real app lifespan/source hooks, immediate import, nonblocking shutdown,
and unreadable-book isolation. Old manual transfer/migration tests also pass.

The local `diki-remote:scheduling` Linux/amd64 image built and passed a default-
entrypoint smoke test under a 256 MiB limit. Authenticated status exposed
`schedulingVersion: 1`; an empty finite snapshot/drain worked with zero upstream
requests and external networking disabled. All implementation tests used temporary
data and fake integrations; no personal inventory was exported and the live worker
was not changed.

## Node connection indicator

The homepage header has a clickable Node status pill beside Anki and Gemini.
It checks once when that header mounts and again on click; there is no interval
polling. Checking is independent of the existing home/Anki status request, so a
slow or unavailable node does not hold up the rest of the page.

The browser calls `/backend/remote-node/health`. The local backend uses the
configured URL/token for an authenticated, read-only `GET /v1/status`, with short
2-second connect/3-second read timeouts, certificate verification, redirects
disabled, and the existing bounded JSON reader. Credentials and remote response
contents are not forwarded to the browser.

Green means the authenticated node API responds with a supported status shape;
red means it is unavailable or the check failed. Checking/not-configured states
use a neutral indicator. If the local backend cannot answer, the label is Unknown
rather than claiming the remote node is down. Hover/focus details provide the
result and last-check time. A reachable older worker can be online while still
requiring an update for automatic scheduling; the details explain this.

API health is separate from Diki reachability, cooldown, and queue progress. The
check submits no jobs, fetches no dictionary content, and triggers no transfer.

Verification: the full project check passed with 63 formatted Python files, zero
Pyright errors/warnings, 283 tests (277 passed, 6 skipped), and frontend production
build. Seven new offline regressions cover bounded/authenticated read-only status,
missing configuration, authentication failure without secret exposure, timeouts,
malformed status, older-worker/cooldown distinction, and the separate local route.
All HTTP was fake; no live node, Diki, or Anki request was used for these checks.

## Deployment and verification

The [deployment guide](../../deploy/northflank/README.md) owns configuration,
commands, persistent-volume requirements, limits, and recovery procedures.
Northflank account entitlement, cost, deployment, and live Diki connectivity must
be recorded separately from local implementation checks.

The restored regression suite covers staging, corruption, authentication, budgets,
storage pressure, durable cleanup, lost ACKs, explicit retries, real subprocess
SIGKILL recovery, and HTML-free audio instructions. Port regressions cover aliases,
case-distinct recordings, current non-entry page types, and old alias metadata.
Standard checks use fake integrations and temporary data. Four real loopback HTTP
streaming tests run only with explicit `RUN_LOOPBACK_TESTS=1`; the guarded offline
runner disables them even if that variable was inherited.

Verification on 2026-11-22: `.ankiFac/bin/python -m tools.check` passed lint,
formatting, Pyright, 251 tests (245 passed, 6 skipped), and frontend build.
The four explicit loopback streaming tests passed separately; `git diff --check`
also passed. No live Diki/Anki request or personal-data mutation was performed.
The original stash remains available. No commit, push, or cloud resource creation
was performed. The owner clarified that deployment is a later goal, outside the
restoration/compatibility-update request.

### Subsequent local container verification

On 2026-11-22, the owner requested an image while configuring the Northflank
service. GitHub `main` and the clean local checkout both contained `089a609`.
Built `diki-remote:089a609` with:

```bash
docker build --platform linux/amd64 -f deploy/northflank/Dockerfile -t diki-remote:089a609 .
```

The default entrypoint then passed a local smoke test under a 256 MiB memory limit:
health returned protocol 2, unauthenticated status returned 401, authenticated
status reported an empty queue and zero upstream requests, and shutdown succeeded.
The disposable test container used external networking disabled and a temporary
`/data` mount; no personal data or production secret was used. This verifies local
image build/startup, not persistent-volume recovery, remote fetch performance, or
Northflank deployment. No image was pushed to a registry. Northflank's Combined
service can build directly from the committed Dockerfile using context `/` and
location `/deploy/northflank/Dockerfile`.

### Manual live verification — 2026-11-23

The owner deployed `089a609` with persistent `/data`. `replenish` reused saved HTML
and imported an 11,446-byte recording. An explicitly requested separate-agent test
then submitted `Standoff` and `Eggnog` sequentially, waited 60 seconds each, pulled,
and verified newly downloaded HTML/MP3 sizes, digests, meanings, and recording
provenance. Four upstream requests produced both pairs; ACKs reported zero cleanup
pending and the node retained no payloads. Source queues stayed unchanged. This
verifies the original manual path, not live operation of the new scheduler.
