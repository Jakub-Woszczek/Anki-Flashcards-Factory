# Remote Diki downloader

Last updated: 2026-11-22. Implementation restored and ported; deployment pending.

The owner requested restoring the Northflank downloader from stash
`8d5a6b5570d15ae80eb73ea66650c7ab51c0b13e` (index parent `12bc1d6`) while
preserving its behavior. The worker is an optional remote dictionary-preparation
component; the browser, backend, queues, and Anki remain on the Mac.

## Preserved workflow

1. The Mac explicitly submits missing work from text lists or command-line words.
   It neither consumes nor rewrites the source queues.
2. A single resident worker fetches directly from Diki into a durable `/data`
   volume, including SQLite jobs, budgets, retries, and transfer records.
3. Completed work stays remote until an explicit Mac `pull`. Nothing pushes to
   the Mac and no submit/pull schedule is installed automatically.
4. Pull stages and validates the complete manifest and payloads, imports into the
   shared local cache, then re-reads the imported data before sending an ACK.
5. The server commits delivery before deleting payloads. Stable manifests, local
   journals, and delivery tombstones support interrupted transfers and lost ACKs.

The Mac never uploads cached HTML. If only audio is missing it submits bounded
advertised recording URLs, the local HTML digest, and selector version. Missing
recording links are recorded locally; exhausted remote URLs produce a small
no-audio receipt. Audio-only transfers require the original local HTML.

Default budgets remain 100 upstream attempts and 3,600 active work seconds per
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

This restores the remote queue/transfer infrastructure. It does not add the
bounded main/book buffers or existing-Anki-note inventory discussed in
[offline preparation](offline-cache.md#preparation-priority-a-buffer-then-existing-notes).

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
restoration/compatibility-update request. Container build/runtime and cloud
deployment remain unverified.
