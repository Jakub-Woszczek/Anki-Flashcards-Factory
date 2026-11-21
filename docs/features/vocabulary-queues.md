# Vocabulary sources and queue lifecycle

Last updated: 2026-11-21.

Status: file-backed processing implemented as `Q-001`. The owner approved the
implementation and the UI simplifications below after the handbook walkthrough.
Historical snapshot behavior is recorded in [the checkpoint](../review.md).

## Purpose and authority

Main and book vocabulary files are mutable pending queues, not input to a second
persisted queue. They shrink as individual entries are resolved. A book file is
not an untouched archive of all original Kindle highlights.

- Main source: `words_to_add/words_to_add.txt`.
- Book sources: `.txt` files under `words_to_add/`, including subdirectories.
  The current Fablehaven file is `words_to_add/Fablehaven_flashcards_clean.txt`.
- One nonempty line is one pending entry; file order is processing order.
- UTF-8, an optional initial BOM, CRLF/LF, blank lines, and a missing final newline
  are supported. Whitespace is trimmed for presenting/looking up the current word;
  consuming it preserves the other original bytes.
- File discovery accepts only files resolved inside the source directory; aliases
  to the same resolved file share one workspace. Outside symlinks are excluded.

See [project purpose](../project.md), [ADR 0002](../decisions/0002-per-entry-vocabulary-resolution.md),
and [ADR 0004](../decisions/0004-file-backed-word-queues.md).

## Homepage and intake

The homepage lists actual source files with current nonempty-entry counts,
including empty sources. Open a source to process it. Refresh/reopen discovers new
files and CLI additions; successful completion also reads the next entry from the
current file. There is no continuous filesystem push into an already displayed word.

Maintain vocabulary using the text files and dictionary CLI capture. The owner
explicitly retired these browser capabilities:

- Pasting words or uploading a file to create an independent queue.
- Queue naming and repeated main-file snapshot creation.
- Homepage queue editing, add/delete/reorder, and diff UI.
- Deleting saved queues through the homepage.

There is one persisted workspace association per source file. Anki target settings
and an optional unfinished-word draft can persist independently of pending words.
There is no SQLite pending-word/order mirror.

## Completion actions

| Action | Source result | Anki result |
| --- | --- | --- |
| Create and continue | Consume the current source entry after verified save | Create note |
| Update and continue | Consume the current source entry after verified update | Update existing note in place; preserve current card decks |
| Discard from queue | Consume the current source entry | No Anki mutation |
| Create custom card | Consume the current source entry after verified save | Create the configured manual note |
| Suspend duplicate and continue | Consume the current source entry after successful suspension | Suspend the existing note's cards |

There is no generic skip-for-later action in vocabulary processing. Exit before
resolving a word to leave it pending. **Discard from queue** also covers deciding
that an existing Anki note already adequately covers the current word. A separate
"Keep existing card" action would have the same effect and was removed.

The owner also retired **Delete duplicate note**: update-in-place is the supported
overwrite workflow. Queue discard does not delete an Anki note or its cards.

Tag/flag review remains a separate, temporary browser traversal. Its **Next review
item** action does not consume a vocabulary file, and its saves no longer perform
implicit main-list cleanup.

### Save confirmation

Current implementation still requires successful follow-up Anki verification for
create/update/custom saves. The separately accepted warning-and-continue change
for acknowledged creation with failed confirmation remains pending as `S-001`.
See [Anki completion semantics](../contracts/anki.md#acknowledged-creation-with-failed-follow-up-confirmation).

## Resolve one original entry at a time

The original source entry and resolved dictionary word are distinct. If the first
line is `causes`, selecting/saving `cause` consumes that original `causes` line.
It does not remove another `cause`/`causes` line in the same or another source.

Repeated lines count as separate pending entries and receive separate identities
as they are reached. Do not stem, automatically equate variants, or scan other
entries for eager Anki deduplication. The owner evaluates each entry at its turn.

The intended Anki English value remains the relevant Diki headword. This refactor
fixes raw-to-source consumption; it does not implement a new automatic canonical
headword resolver or a complete Anki matching policy. See [Diki rules](../contracts/diki.md).

## Concurrent capture, stale requests, and recovery

Concurrent dictionary CLI capture is expected. Source operations and cooperating
appends use a stable file lock and atomic replacement. SQLite contains only the
current entry's identity, byte range, and source fingerprint, not the word queue.

- An unchanged original file prefix permits new appended entries without dropping
  the current draft or excluding the appended vocabulary from later processing.
- Current-entry requests carry an entry ID. Requests from an old browser view
  cannot save, discard, or apply a draft to the next occurrence, even if its text
  is identical.
- Other observed content edits invalidate the entry reference and draft. Reload
  the source before continuing; the app does not guess which changed line to remove.
- Every consumption archives the exact removed line and a pre-removal file backup
  under `data/archives/source-<entry-id>.txt.bak`. A durable `source_resolutions`
  receipt links the source workspace, entry, outcome, and Anki save where applicable.
- Before/after hashes, sizes, and file identity allow retry across the file-write /
  SQLite-commit boundary without consuming a second occurrence. An ambiguous
  external change preserves the file and reports the pending receipt/backup for
  investigation rather than guessing.
- A verified Anki save followed by failed source removal remains retryable without
  blindly creating another note. Save intents include source-entry identity.

The explicit legacy `tools.clean_words_to_add` bulk command remains separate from
normal processing. Its `--resume` retries its own `already_in_anki` operations,
not source-workspace or review saves.

## Unfinished-word drafts

Draft autosave/resume remains a convenience associated with the current entry.
The owner accepts reselecting translations; optional removal is still `Q-002`.
It is separate from source queue ownership, Diki resource caching, and save recovery.
Changing the observed source contents clears a stale draft; append-only growth does not.

## Book content and remaining decisions

Book files currently contain one word/phrase per line and can have artifacts such
as quotes. The example `"flimsy"` → `flimsy` is confirmed, but no general punctuation
stripping contract has been agreed. This refactor does not automatically rewrite
book vocabulary or broaden the existing `en_word` syntax contract.

Future import-format ideas and broader dictionary-informed matching remain future
work. Browser upload/paste is deliberately retired rather than a missing feature.

## Migration and verification evidence

On 2026-11-21, read-only comparison found one legacy main add queue (394 pending
entries) and no imported add queues. At the owner's request, its 25 entries absent
from the main file were appended at the end in queue order. A second comparison
found no remaining SQLite-only entries. Main-file pending count became 645;
Fablehaven had 682. Counts are a migration snapshot, not fixed expectations.

The local database was backed up to `data/archives/pre-q001-20261121.sqlite3`.
Migration reused the main source's existing target settings, cleared its old draft,
and retired its copied queue rows. Older review metadata is inactive history.
No source entries were consumed and no live Anki/Diki requests were made during
migration. Routine regression verification is offline with temporary files/fake Anki.

Verification on 2026-11-21: `python -m tools.check` passed lint, formatting, Pyright,
132 offline tests (2 opt-in live tests skipped), and frontend TypeScript/build.
Regressions include current-entry API validation, concurrent writers/workspaces,
external edits during lookup/audio preparation, and file-write/SQLite crash boundaries.
