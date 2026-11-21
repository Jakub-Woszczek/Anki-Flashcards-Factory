# ADR 0004: Source files are the word queues

Date: 2026-11-17.

Status: Accepted; implemented as `Q-001` on 2026-11-21. The owner refined and
approved the implementation scope after the original walkthrough.

## Context

The owner treats `words_to_add/words_to_add.txt` itself as the pending queue.
At decision time the UI instead copied words into an independently persisted SQLite queue.
That duplication does not match the original intent and introduces unnecessary
state and synchronization problems, particularly while CLI capture appends words.

## Decision

Use the word source file as the authoritative queue. The redundant
SQLite-backed add-queue/snapshot logic was retired in the Q-001 implementation.
Process and consume entries from the source rather than maintain a second queue
that must mirror it.

The previously confirmed lifecycle still applies: source entries remain pending
until individually resolved, and concurrent appends must be preserved. Main and
book files were already established as consuming word sources; this decision
does not choose a new Kindle format or book-location convention.

## Rationale and consequences

- The file already provides the word order and pending-work state the owner needs.
- A duplicated database queue adds code and synchronization without a needed
  independent workflow model.
- Treat the former SQLite queue as an implementation mismatch, not an accepted
  product requirement to preserve.
- No separate source-to-snapshot synchronization feature is desired.
- This decision is about word-queue storage. It does not decide whether an
  unfinished word's draft or target settings need separate persistence, nor does
  it request removing unrelated note indexes, save journals, or resource metadata.
- The original interview deferred retirement/bookkeeping details. Q-001 subsequently
  implemented exact-entry consumption and migration as recorded below.

Follow-up in batch 16: unfinished-word draft recovery is optional convenience;
redoing translation selections is acceptable. Removing that convenience is a
possible simplification (`Q-002`), not a firm requirement. Other storage purposes
are not determined by this answer. See the
[draft clarification](../features/vocabulary-queues.md#unfinished-word-drafts).

## Implementation and owner refinements — 2026-11-21

- Discover the main/book `.txt` sources in `words_to_add/` and process their current
  contents. Retain a workspace's target settings and one entry-bound optional draft.
- Retire browser pasted/uploaded queue creation, queue naming, homepage queue
  editing/diffs, and queue deletion. Vocabulary is maintained in files/CLI capture.
- Use **Discard from queue** as the sole skip-like vocabulary action. Accepting an
  already-covered word has the same file/Anki effect and needs no keep-existing button.
- Remove duplicate Anki-note deletion; keep the update-in-place workflow.
- Consume only the original current source occurrence, including when dictionary
  lookup changes its spelling. Other occurrences and sources remain pending.
- Preserve concurrent CLI appends using shared locks/atomic writes. Entry IDs and
  durable before/after removal receipts prevent stale requests or retries from
  consuming the next identical occurrence. Ambiguous external changes preserve data.
- Keep save verification separate from exact source consumption. Tag/flag review
  has no source entry and performs no implicit main-file cleanup.

The owner approved appending the 25 legacy SQLite-only main-queue entries to the
main file before retiring the copied queue. The migration preserved target settings
and retained a local database backup. See [queue migration evidence](../features/vocabulary-queues.md#migration-and-verification-evidence).

The documentation-only constraint applied to the original walkthrough. Q-001 was
separately authorized for implementation; `Q-002` draft removal remains optional
and `S-001` failed-confirmation simplification remains a separate pending task.

See [vocabulary queue rules](../features/vocabulary-queues.md) and
[the walkthrough checkpoint](../review.md).

Supersedes: any inference that the former persisted snapshot queue is intended
architecture. Superseded by: none.
