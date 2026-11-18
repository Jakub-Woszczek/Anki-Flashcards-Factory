# ADR 0004: Source files are the word queues

Date: 2026-11-17.

Status: Accepted as intended architecture; implementation deferred as `Q-001` in
the root [to-do list](../../to-do).

## Context

The owner treats `words_to_add/words_to_add.txt` itself as the pending queue.
The current UI instead copies words into an independently persisted SQLite queue.
That duplication does not match the original intent and introduces unnecessary
state and synchronization problems, particularly while CLI capture appends words.

## Decision

Use the word source file as the authoritative queue. Remove the redundant
SQLite-backed add-queue/snapshot logic in a separate implementation session.
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
- Treat the current SQLite queue as an implementation mismatch, not an accepted
  product requirement to preserve.
- No separate source-to-snapshot synchronization feature is desired.
- This decision is about word-queue storage. It does not decide whether an
  unfinished word's draft or target settings need separate persistence, nor does
  it request removing unrelated note indexes, save journals, or resource metadata.
- Details of retiring existing sessions and implementing source-entry consumption
  belong to the later refactor, not the current interview.

Follow-up in batch 16: unfinished-word draft recovery is optional convenience;
redoing translation selections is acceptable. Removing that convenience is a
possible simplification (`Q-002`), not a firm requirement. Other storage purposes
are not determined by this answer. See the
[draft clarification](../features/vocabulary-queues.md#unfinished-word-drafts-optional-convenience).

## Implementation boundary

The owner explicitly instructed that behavior changes mentioned during this
walkthrough must be recorded as todos and implemented separately. No application
or database behavior is changed by recording this ADR.

See [vocabulary queue rules](../features/vocabulary-queues.md) and
[the walkthrough checkpoint](../review.md).

Supersedes: any inference that the current persisted snapshot queue is intended
architecture. Superseded by: none.
