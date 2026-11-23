# ADR 0009: Automatic remote preparation with immediate background import

Date: 2026-11-23. Status: accepted and implemented locally; worker rollout separate.

## Decision

1. Prepare the first **100 pending nonempty occurrences in every vocabulary file**,
   in source order, selecting before deduplication. Invalid/duplicate occurrences
   consume positions; failures do not extend the window. The downloader never
   consumes source queues.
2. Buffer preparation includes HTML and advertised pronunciation audio. Reconcile
   asynchronously at startup and after successful source advancement: save,
   discard, custom-card completion, and successful removal retry. Unresolved/failed
   operations and review-only saves do not advance the window. Notifications may
   coalesce into a scan of current files.
3. Existing-note coverage uses a one-time exported English inventory, following
   the documented normal note-type scope and excluding Diki-missing/image-only
   types. Export is explicit/read-only, reports unprocessable values, and never
   modifies notes. Ordinary startup does not scan Anki.
4. Request **only missing HTML** for that inventory, reusing partial local coverage.
   Eligible buffer jobs precede eligible coverage jobs. Running HTTP requests are
   not preempted; retries, cooldowns, and all existing budgets/limits remain.
5. At application startup, perform one finite drain of ready job generations
   captured by the server. Do not wait/poll for jobs that finish later. Source
   workspace changes do not start another drain.
6. Download each batch into its durable journal, validate it, **immediately merge
   into cache, verify, and ACK in the same background task**. Existing short cache
   locks/atomic writes are sufficient. There is no exit-time import or deliberately
   deferred ACK; the owner explicitly rejected that proposed design.
7. Exit signals cancellation without joining remote network waits. Interrupted
   downloads/imports/ACKs recover from journals next launch. Existing Anki sync is
   separate and unchanged.
8. Preserve retained rolling snapshots without routine refresh. Automatic imports
   keep valid local snapshots that appeared after submission, validate recording
   provenance against retained HTML, and durably record reconciliation before ACK.
   Original remote bytes remain staged until ACK. Changed audio-only HTML context
   is still an error, not permission to guess.

## Resource goals and compatibility

A word can belong to both priorities. Promote queued/running coverage goals when
audio becomes required. Never mutate an issued manifest: ready/batched/delivered
HTML-only work can gain audio through a new generation, reusing retained HTML or
Mac-supplied recording URLs. Duplicate old ACKs cannot delete newer work.

Authenticated status advertises `schedulingVersion: 1`; payloads remain protocol 2
with existing protocol-1 recovery. Preserve manual submit/status/pull behavior.
An old worker produces a clear scheduling error instead of semantic fallback.
Accepted-goal receipts avoid repeated submissions but do not count as local cache
coverage or authorize automatic replay after volume loss/cache deletion. Terminal
failed jobs and deliberate redownloads retain their explicit recovery flags.

See [remote preparation](../features/remote-downloads.md) and
[offline coverage](../features/offline-cache.md). This refines ADR 0003/0004 without
changing dictionary identity, translation selection, or stored-field contracts.
