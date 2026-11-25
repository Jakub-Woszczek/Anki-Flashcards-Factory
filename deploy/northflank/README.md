# Remote Diki downloader on Northflank

One always-on service owns durable priority queues and a transfer outbox. The
Mac submits missing work, then downloads completed HTML/MP3 through one automatic
startup drain or manual `pull`. Each batch is immediately imported and ACKed in
background. Anki and the application's database stay on the Mac.

**Rollout:** the original `089a609` worker was deployed and its manual HTML/MP3
path verified live on 2026-11-23. The new automatic scheduler requires this updated
worker and a Mac client with matching scheduling support; its live rollout is
separate from implementation checks. Account free-allowance coverage remains
unverified. The original Linux/amd64 image built
successfully on 2026-11-22, and its default entrypoint passed a local health/auth
smoke test within a 256 MiB limit, with external networking disabled and a temporary
test mount. This does not verify persistent-volume recovery or remote fetching.
The restored implementation uses the current shared dictionary parser and data
paths. Local tests use fixtures, temporary data, and explicit loopback HTTP.
See [the feature record](../../docs/features/remote-downloads.md) for current
verification and deployment status.

## $0 recurring cost: verify before creating resources

Public information checked on **2026-11-12**:

- [Pricing](https://northflank.com/pricing) advertises an ongoing **free Sandbox**,
  no card required, always on, with up to **$20/month of Northflank Cloud
  resources**, 2 services, 2 jobs, and 1 database. Its feature table includes
  persistent volumes. This is distinct from a time-limited promotional credit.
- The same page lists persistent disk at $0.11657/GiB/month and egress at
  $0.06/GB. Feature availability alone does **not** establish that a particular
  volume or transfer is covered at $0 in this account.
- [Compute plans and quotas](https://northflank.com/docs/v1/application/billing/resource-plans-and-quotas)
  says account/project limits can differ, and free projects have separate limits.
- [Persistent volume documentation](https://northflank.com/docs/v1/application/databases-and-persistence/add-a-volume)
  describes single-read/write volumes that survive container replacement.

Before any deployment, record these facts from the **actual account/dashboard**
(or obtain confirmation from Northflank support where the UI is ambiguous):

| Required fact | Current verification |
| --- | --- |
| Account/project is on ongoing Sandbox, not PAYG or expiring credits | Not verified |
| Available service slot and smallest suitable CPU/RAM plan | Not verified |
| Persistent service-volume entitlement, minimum size and monthly allocation | Not verified |
| Compute + disk + builds/build storage + egress + other existing resources stay within the recurring free allowance | Not verified |
| What happens at the allowance limit; no automatic paid overage/upgrade | Not verified |
| Estimated recurring amount for this complete configuration is $0 | Not verified |

**Do not deploy if any required component needs recurring payment or if overage
behavior is unclear.** Do not substitute ephemeral storage: losing the queue,
budgets, or delivery tombstones would cause duplicate downloads. A mounted
filesystem check is a startup guard, not proof of a provider's durability or
billing terms. The downloader's quotas below cannot enforce a hosting bill.

## Service configuration (after account verification)

Use a combined build/deploy service or a deployment service with this image:

1. **Build context:** repository root (`.`).
   **Dockerfile:** `deploy/northflank/Dockerfile`.
   In the Northflank creation form, enter build context `/` and Dockerfile
   location `/deploy/northflank/Dockerfile`, then reload the Dockerfile preview.
   Its Dockerfile-specific ignore file limits the uploaded context; the image
   copies only dictionary modules, deployment Python files, and dependencies.
   Personal `.env`, word lists, cache, Anki data, and application databases are
   excluded. The worker fetches directly from Diki; it does not use the retired
   Cloudflare relay. The shared path helper and `python-dotenv` are included as
   import dependencies; the server uses its explicit `/data` root.
2. Choose the smallest account-eligible compute plan with sufficient memory.
   `nf-compute-20` (0.2 vCPU / 512 MiB) is a starting candidate, **not a verified
   free entitlement or a measured memory guarantee**. Check metrics before
   submitting a large queue.
3. **One replica, one Python/Uvicorn process, one resident worker.** Keep the
   image's command: `python -m deploy.northflank.app`. Do not add Gunicorn
   workers, Uvicorn reload, autoscaling, or another process sharing `/data`.
4. Mount a dedicated persistent **single-read/write** volume at **`/data`**.
   Use the smallest verified free allocation that fits payloads, SQLite, and
   headroom (for example 1 GiB if offered). This contains `index.sqlite3`,
   `html/`, `audio/`, budgets, locks, manifests, and delivery receipts. Preserve
   the entire volume on restart/redeploy. Do not enable `REMOTE_ALLOW_EPHEMERAL`.
5. Create a runtime secret `REMOTE_API_TOKEN`, generated locally:

   ```bash
   python -c 'import secrets; print(secrets.token_urlsafe(48))'
   ```

   Store it in Northflank runtime secrets and the Mac's ignored `.env`. It must
   be 32–256 printable ASCII characters without spaces. It is an application
   token, not a Northflank account/API token. Do not put it in build arguments,
   source files, command-line arguments, or URLs.
6. Set runtime variables from [`.env.example`](.env.example), retaining the
   conservative defaults initially. Expose HTTP port **8080** behind Northflank's
   generated HTTPS hostname. Use **`GET /health`** for health checks; health and
   status requests never initiate dictionary downloads. Allow about 30 seconds
   for graceful shutdown.
7. The entrypoint initially owns the mount root as UID/GID 10001 and drops root
   privileges before opening the queue or serving HTTP. Existing data must also
   be readable/writable by 10001; it deliberately does not recursively chown
   arbitrary existing files. Provision ownership if importing a volume backup.

The API uses constant-time Bearer-token authentication before reading API bodies,
strict input schemas, 2 MiB/15-second POST-body limits, SHA-256 manifests, bounded
artifacts, and validated filenames/sources. Clients validate HTTPS certificates
and refuse redirects; HTTP is permitted only for loopback testing. Runtime
secrets avoid embedding credentials in the image. No custom certificate or
cryptographic key material is shipped.

## Mac configuration and commands

Activate the project's Python environment with its normal requirements installed.
Add to the existing root `.env` (preserve its other settings):

```dotenv
DIKI_REMOTE_URL=https://your-service-generated-hostname.code.run
DIKI_REMOTE_TOKEN=the-same-generated-runtime-secret
ANKI_FACTORY_DATA_DIR=../Anki-Flashcards-Factory-data
```

Run from the repository root:

```bash
# All unique words under ANKI_FACTORY_DATA_DIR/words_to_add/, including subfolders.
python -m tools.diki_remote submit

# Explicit words/phrases, or a selected list directory.
python -m tools.diki_remote submit take deliverance
python -m tools.diki_remote submit "take off"
python -m tools.diki_remote submit --words-dir words_to_add/books

# Inspect the queue, today's budgets, cooldown, and first 20 failed words.
python -m tools.diki_remote status

# Explicit transfer: stage, validate, import, re-read, then ACK.
python -m tools.diki_remote pull
python -m tools.diki_remote pull --max-batches 1

# Global options go BEFORE the subcommand; use the same cache for submit/pull.
python -m tools.diki_remote --cache-dir diki_cache pull

# Explicit one-time read-only export from normal Anki vocabulary note types.
python -m tools.diki_remote export-coverage

# Optional manual HTML-only inventory submission, or import a prepared word file.
python -m tools.diki_remote coverage
python -m tools.diki_remote coverage --file existing-words.txt
```

### Ready HTML breakdown in status

`python -m tools.diki_remote status` retains the numeric `jobs.ready` and also
reports:

```json
"readyHtml": {
  "total": 271,
  "categories": {
    "entries": 250,
    "suggestions": 8,
    "related": 5,
    "collocation": 3,
    "not_found": 5,
    "unknown": 0,
    "missing": 0,
    "unusable": 0
  }
},
"readyAudioOnly": 0
```

These example numbers are illustrative. The categories use the application's
shared primary-result classifier. HTML categories sum to `readyHtml.total`, and
that total plus `readyAudioOnly` equals the ready-job count. This includes jobs in
an unacknowledged transfer; they leave the counts only on ACK or requeue. Audio-only
jobs, including no-audio receipts, are counted separately.

Redeploy the worker to add these fields. Existing ready HTML is classified once
from retained bytes during initialization, without dictionary requests or changes
to frozen manifests. `missing`/`unusable` distinguish unavailable or unverifiable
retained HTML and are reconsidered on restart. Subsequent status checks read saved
classification metadata, not HTML files. See [the feature record](../../docs/features/remote-downloads.md#ready-html-categories--2026-11-25).

### Automatic application scheduling

With both remote settings configured, a normal app launch prepares the first
**100 nonempty entries per vocabulary file**, counting duplicates before
deduplication. Missing buffer HTML/audio has priority over the saved existing-note
HTML inventory. Replenishment runs off-thread after successful save/discard/source
removal and reconciles at startup for file edits or interrupted submissions.

The existing-note inventory is `ANKI_FACTORY_DATA_DIR/diki_cache/coverage/inventory.json`.
`export-coverage` explicitly reads the two normal note types, excluding the missing-
Diki and image-only types, preserving casing and reporting invalid English fields.
Ordinary app startup reads that file, not Anki. Existing partial HTML coverage is
reused. `coverage --file` loads an owner's UTF-8 word-per-line file outside consuming
queues. Failed coverage work can be explicitly retried with `coverage --retry-failed`;
`coverage --redownload-delivered` restores delivered HTML missing locally.

Once per backend launch, a background worker recovers journals, snapshots current
ready remote jobs, then downloads/imports/verifies/ACKs each batch immediately.
It does not wait or poll for work finishing after the snapshot. Newly imported
vocabulary is available during the session. Exit signals cancellation without
joining network waits; recovery handles interruption between any of those steps.

Worker status must advertise `schedulingVersion: 1`; update/redeploy the worker
while preserving `/data` before enabling the new Mac scheduler. An old worker
remains usable manually and causes a clear automatic-preparation error, not
fallback to unbounded submission or another import policy. Manual `submit` still
scans complete source files; the 100-entry limit applies to automatic scheduling.

The default local cache is `ANKI_FACTORY_DATA_DIR/diki_cache/`. Explicit relative
`--words-dir` and `--cache-dir` paths resolve against that data root, like the local
prefetch tool. Do not set the retired `DIKI_WORDS_DIR` or `DIKI_CACHE_DIR` variables.
Case-distinct words remain separate. Imported resolved aliases seed missing local
canonical-headword resources, preserving existing independent snapshots. The server
retains only requested-word payloads, so ACK cleanup does not leave alias copies.

`submit` checks the local cache and uses the existing recording parser on the
Mac. **Cached HTML is never uploaded by this command**, regardless of its size:

| Local resources | Submitted work |
| --- | --- |
| HTML + MP3 | None |
| HTML + current confirmed no-audio result | None |
| Suggestion/no-results HTML | None |
| HTML, no MP3, no advertised recording links | None; durably record no-audio locally |
| HTML, no MP3, advertised recording links | Audio-only job: word, ordered URLs, HTML checksum, parser version |
| MP3, no HTML | HTML only |
| Neither | HTML then MP3 |

Audio-only jobs avoid server HTML fetching, parsing, storage, and HTML transfer
back to the Mac. They contain at most 32 canonical Diki recording URLs (2,048
characters each). Oversized/invalid plans fail explicitly rather than falling
back to HTML uploads/downloads. Advertised URLs are not guaranteed to exist:
the server tries candidates in the parser's preferred order, advancing its
durable cursor after each 404. There are no preliminary HEAD/probe requests.
If all candidates return 404, it exports only a small no-audio receipt, with no
HTML or MP3 payload. The local negative result is tied to the HTML checksum and
discovery version, so changed HTML or a new parser version invalidates it.

Submission output includes `audioOnly` (audio-only instructions offered to the
server, including already-known jobs) and `noAudioLocal` (newly confirmed local
pages with no advertised recordings). `alreadyCached` also includes these new
local negatives. Legacy HTML-seeded jobs remain supported for queue recovery,
but the current Mac command never sends a seed.

Repeated submission skips already satisfied/accepted resource goals. Higher-priority
buffer requests can promote HTML-only coverage and add missing audio. Issued
manifests remain immutable; follow-up generations preserve reusable HTML and old-
ACK isolation. Failed jobs still require explicit retry; delivered resources that
are missing locally still require explicit redownload unless the request adds a
genuinely missing audio goal.
Delivered tombstones remain even after server payload deletion. The server
continues work while the Mac is asleep; it never pushes files to the Mac.

`submit`, `pull`, and `status` do not fetch from Diki on the Mac. The normal
application/interactive CLI still follows its own cache-first online behavior;
use `DIKI_OFFLINE=1` locally if missing entries must never trigger local Diki
requests. When switching background work to this server, unload any existing
local prefetch launchd agent using the root README's commands. Automatic preparation
is application-scoped; no additional launchd job or periodic remote pull is installed.

## Transfer and durability contract

Only complete requested work is exported: HTML+MP3, HTML+confirmed no-audio,
suggestion/no-results HTML, explicitly requested HTML-only, or **MP3-only / an
audio-only no-audio receipt** referring to the original local HTML. Pending
partial words remain server-side; audio-only work never falls back to HTML.

New batches use transfer protocol **2**. This client/server can still recover
existing protocol-1 HTML-containing batches unchanged; existing SQLite queues
gain the audio-plan column without losing jobs, manifests, budgets, or receipts.
Update both client and server for audio-only work; an older client rejects new
protocol-2 transfers rather than importing them incorrectly.

1. The server creates a stable manifest (up to 10 words / 32 MiB of payloads /
   512 KiB of manifest JSON). Long URL lists are split into smaller batches. The oldest
   unacknowledged manifest is returned unchanged across requests/restarts.
2. `pull` journals the manifest and each completely received, validated artifact
   under `CACHE/remote-imports/<server-origin-hash>/<batch-id>/`. Files have
   bounded sizes, SHA-256 checksums, allowed source URLs, and HTML/MP3 checks.
   For audio-only work, it checks that the original local HTML still exists,
   matches the submitted checksum, and yields the same recording URLs **before
   transferring MP3 bytes**, then validates that context again before ACK.
   The complete batch is validated before any cache import.
3. Import uses atomic replacement, file and directory fsync, then SQLite
   transactions (`synchronous=EXTRA`, and `fullfsync=ON` on supported systems).
   Every imported artifact is re-read and validated before ACK. Automatic imports
   preserve a valid independent local snapshot that appeared since submission,
   validate recording provenance against the retained HTML, and journal that
   reconciliation while retaining original staged bytes until ACK. Audio-only
   source-context mismatches remain unresolved errors.
4. The client sends authenticated ACK with the exact manifest digest. Only after
   the server commits the receipt and delivery states does it unlink payloads
   and sync their directories. Deletion failures leave `cleanupPending` and are
   retried on later cycles/ACKs. Receipts/tombstones remain in SQLite.
5. The local journal is removed after the ACK response. If the response is lost,
   the next startup drain or explicit `pull` reuses committed cache/staged content and repeats the
   idempotent ACK. It does not need server files that have already been deleted.

Downloads alone never delete server payloads. Interrupted pulls retain fully
validated staged files; an incomplete individual file restarts at byte zero
(there is no HTTP Range support). Keep the journal and server URL unchanged
until recovery completes. A transfer cannot provide exactly-once upstream HTTP:
a hard kill after an HTTP response but before its cache commit can require a
repeat attempt. Persisted reservations and attempt limits bound that case.

## Budgets and pacing

| Variable | Default | Meaning |
| --- | --- | --- |
| `REMOTE_REQUESTS_PER_DAY` | 400 | All reserved upstream HTTP attempts, including failures/404s |
| `REMOTE_WORK_SECONDS_PER_DAY` | 3600 | Elapsed active work-slice time, including pacing waits |
| `REMOTE_BATCH_SECONDS` | 180 | Maximum reserved work slice; must exceed 15 seconds |
| `REMOTE_BATCH_WORDS` | 10 | Words attempted per cycle |
| `REMOTE_MAX_PENDING_MB` | 128 | MiB of indexed HTML/MP3 payloads (not total volume size) |
| `REMOTE_POLL_SECONDS` | 60 | Idle interval between cycles |

The daily request default was raised from 100 to 400 on 2026-11-24. For an existing
deployment with `REMOTE_REQUESTS_PER_DAY=100` set explicitly, change that runtime
variable to `400`; it overrides the code default even after redeployment. Redeploy
the worker to apply the configuration and confirm `requestLimit: 400` with
`python -m tools.diki_remote status`.

The separate 3,600-second active-work budget still applies and includes pacing
waits, so 400 is an attempt ceiling, not a daily throughput guarantee.

Both daily budgets reset at midnight **UTC** and survive restarts. HTTP attempts
are reserved before network I/O; a crash cannot refund them. A full runtime
slice is reserved before work, then unused time is refunded based on monotonic
elapsed time. Hard crashes conservatively retain the entire reservation.
Runtime is cooperative elapsed worker time, not CPU time, total service uptime,
build minutes, or an exact hosting-credit meter. Socket reads have finite
timeouts and streamed bodies have a checked monotonic deadline; OS operations,
DNS/header handling, and filesystem stalls are not a hard wall-clock guarantee.

Storage checks reserve headroom for a maximum-size response before requesting it
and retain at least 32 MiB free. Small actual files can therefore pause work
before reaching the advertised payload limit. SQLite/receipts, temporary files,
and filesystem overhead are outside `storedBytes`; free-space checks cover
overall pressure. A hard kill can leave unindexed `.download-*` files. Inspect
such files only with the worker stopped; they are not automatically discarded.

Default pacing is 20 seconds ±5 between completed requests, with durable adaptive
backoff. Challenges/403/429 pause for 6–24 hours (or longer `Retry-After`).
Individual failures back off from 30 minutes to 24 hours. Three consecutive
timeouts/5xx add a global cooldown. Budget, storage, and already-active cooldown
pauses do not consume a failed-job attempt. Five failures or recovered hard
interruptions stop a word in `failed`; no automatic infinite retry. Limits of
20,000 unique queue/tombstone words and 5 attempts are currently code defaults.

## Recovery and operational limitations

- **Network/transfer/local disk failure:** fix the cause, then rerun `pull`.
  Successfully staged files are reused; no ACK is sent for an incomplete import.
  If the server already committed an ACK, the journal resolves that same ACK.
- **Request/runtime budget exhausted:** wait for the UTC reset. Polling status
  does not consume upstream requests. Raising a budget is an explicit operator
  decision and does not increase the free hosting allowance.
- **Pending payload storage full:** explicitly `pull` completed transfers.
  If all retained words are incomplete/failed, inspect those words and storage
  before changing limits. A tighter volume must not be "fixed" with ephemeral
  storage or by deleting SQLite state.
- **Failed word:** inspect `failedWords` and fix the cause, then explicitly run:

  ```bash
  python -m tools.diki_remote submit --retry-failed take
  ```

  This creates a new job generation, clears that word's resource retry state,
  and reuses valid server HTML/audio. Global cooldowns and daily budgets remain.
- **Previously delivered word missing on the Mac:** restore the local cache from
  backup first if available. Otherwise explicitly allow a new generation:

  ```bash
  python -m tools.diki_remote submit --redownload-delivered take
  ```

  Only missing local words are submitted. Old duplicate ACKs cannot delete the
  new generation. The flag cannot reset an unacknowledged ready transfer.
- **Corrupt server artifact/manifest (HTTP 409):** the pending outbox stays
  blocked, payloads remain, and no automatic upstream repair/redownload occurs.
  Stop the service, preserve a copy of `/data` and the Mac's journal, and restore
  matching bytes/metadata from a known-good backup. An artifact must match the
  existing manifest's size/digest; the envelope must preserve its original IDs
  and digest. A Mac journal may contain the exact missing bytes/envelope.
  Restart and rerun `pull` after restoration. **There is currently no supported
  discard/requeue command for a corrupt ready transfer.** If no matching copy
  exists, an explicit operator-reviewed repair is required. Do not ACK files
  that were not durably imported or delete the database to force a retry.
- **Audio discovery version mismatch:** update client/server to compatible
  versions; negative results and audio-only instructions are not silently
  trusted across selector versions. Complete pending transfers before changing
  discovery versions.
- **Local HTML changed/deleted during an audio-only job:** `pull` stops without
  ACK or automatic HTML redownload. Restore the original HTML from local backup
  and rerun `pull`; the server retains its completed work. Keep that HTML until
  the transfer journal has been resolved, including after a lost ACK response.
- **Volume loss or stale restore:** queue, budgets, receipts, and tombstones are
  lost or rolled back together and duplicate requests become possible. Back up
  the entire stopped volume consistently, retain local journals/cache, and check
  provider backup costs before enabling any paid snapshot feature.
- **Health versus progress:** `/health` proves API liveness only. Inspect status,
  cooldown, `failedWords`, `cleanupPending`, volume free space, and container
  metrics for progress. Receipts/tombstones do not expire automatically; a
  future maintenance policy is needed if metadata approaches volume/queue limits.

## Local smoke test (no Northflank resource creation)

With Docker running, from the repository root:

```bash
docker build -f deploy/northflank/Dockerfile -t diki-remote:local .
export REMOTE_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker volume create diki-remote-test
docker run --rm --name diki-remote-test -p 127.0.0.1:8080:8080 \
  --mount source=diki-remote-test,target=/data \
  --env REMOTE_API_TOKEN diki-remote:local
```

In another terminal, use that token as `DIKI_REMOTE_TOKEN` and run
`python -m tools.diki_remote --url http://127.0.0.1:8080 status`. An empty queue
makes no Diki requests. For a non-container test, use a dedicated absolute
`REMOTE_DATA_DIR` with `REMOTE_ALLOW_EPHEMERAL=1` and run
`python -m deploy.northflank.app`. That override is for local testing only.
Submitting a word to this running worker **will** initiate real Diki work;
the automated tests below remain offline.

## Regression tests

The server requirements are in `requirements.txt` beside this README. Tests
use the project's development environment and `httpx` for FastAPI TestClient.
Run from the repository root:

```bash
.ankiFac/bin/python -m tools.check
# Explicit local-socket transport checks; no Diki or Anki access.
RUN_LOOPBACK_TESTS=1 .ankiFac/bin/python -m unittest tests.test_diki_remote.TestBoundedHTTPStreaming
git diff --check
```

The standard check uses `tools.test_offline`, which blocks sockets/DNS and disables
both live integration and loopback checks. The in-process remote protocol tests and
fake-transport subprocess crash tests run within that boundary. The four opt-in
loopback tests exercise real HTTP streaming separately.

Tests cover resumable import, lost ACKs, checksum failures, durable deletion
ordering, actual chunked/gzip/trickling/stalled/truncated loopback HTTP streams,
real subprocess SIGKILL recovery, explicit retries, budgets, ownership, backoff,
corrupt server data, and authentication. Audio-only coverage checks no HTML
uploads/fetches/transfers, zero server calls for absent recording links, durable
404 fallback progress, payload-free negative receipts, changed-local-HTML
protection, unsafe URL rejection, mixed batches, and legacy queue migration.
Live Diki tests remain opt-in.
