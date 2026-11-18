# Vocabulary sources and queue lifecycle

Last updated: 2026-11-17.

Specification status: source-file authority, core lifecycle, per-entry evaluation,
and optional draft recovery confirmed. Draft removal is a possible simplification;
exact source-entry bookkeeping remains open below.

Implementation status: mismatch. The current SQLite add-queue snapshot is not the
intended architecture. Replacing it with file-backed processing is deferred as
`Q-001`; book-source consumption and discard also remain incomplete.

Verification status: initially source/test inspection. In batch 10, isolated
completion/recovery tests ran for the deck-preservation fix; this is not acceptance
verification of every intended queue/source lifecycle rule below.

## Purpose and rationale

Both everyday vocabulary and book vocabulary are pending work queues. They shrink
as words are dealt with. A book file is not intended to remain an untouched,
complete record of all highlights simply because it came from a book.

Once a word is successfully added to Anki, the owner should not have to put it
back into the queue. A word already in Anki is also no longer pending. The owner
may reconsider vocabulary collected months earlier and decide not to learn it.
These outcomes apply when evaluating the current entry, not as permission to
scan other queued entries and resolve them in advance.

See [project purpose and sources](../project.md) for the broader context.

## Confirmed intended behavior

### Sources are mutable pending queues

- The main source is `words_to_add/words_to_add.txt`.
- Book-specific vocabulary files are also pending queues.
- Both kinds of source shrink when entries are resolved.
- The source file **is the queue**, not merely input for another persistent queue.
  The owner explicitly rejects duplicated SQLite word-queue state and the need
  to synchronize it with the file.
- Successful addition means the word is in Anki, not merely removed from a browser
  session. For an acknowledged creation followed by a failed confirmation request,
  the owner accepts a warning and normal completion/advancement (`S-001`); successful
  follow-up read-back should not block that case. See the
  [Anki completion rule](../contracts/anki.md#acknowledged-creation-with-failed-follow-up-confirmation).

### Resolution outcomes

These describe semantics, not prescribed button labels or database states:

| Outcome | Intended result |
| --- | --- |
| Successfully added to Anki | Consume the pending word |
| Already in Anki after evaluating the current entry | Consume that pending entry rather than retaining it for later addition |
| Owner decides not to learn the current entry | Remove that entry from its pending source without adding it |

No separate deferral requirement was established by this answer. Do not interpret
the current implementation's generic skip as the intended behavior for all three
outcomes. Removing a pending word is distinct from deleting an existing Anki note.

What counts as an existing Anki match will be defined with Anki identity and
duplicate handling; these queue rules do not decide that matching policy.

### Evaluate one entry at a time

- Processing the current word must not trigger queue-wide or cross-list removal
  of other pending entries. Evaluate those entries when their own turn arrives.
- The owner uses Diki HTML to understand how Diki represents the current word,
  then evaluates redundancy against Anki using that understanding.
- In the owner's supplied Diki page example, queued `causes` leads to headword
  `cause`, which is the intended Anki `en_word`. This is owner-provided page
  evidence, not a new raw-HTML fixture or a general singularization rule.
- Do not infer that raw queued forms are equivalent using stemming, spelling
  similarity, or an apparent shared base word and silently remove them.
- Automatic evaluation of other queued variants is not a current goal. The
  owner's evaluation remains important to deciding whether a word is redundant.
- A word present in Anki can therefore remain in another pending list until that
  particular entry is reached and evaluated. This qualifies the earlier general
  statement that already-added words should leave the queue.

See [ADR 0002: Per-entry vocabulary resolution](../decisions/0002-per-entry-vocabulary-resolution.md).

The raw queued text and the resolved dictionary word are conceptually distinct.
Anki should store the relevant Diki headword: this is **Diki compatibility**.
Completion concerns the current original source entry, rather than using the
resolved spelling as permission to remove other pending entries. The technical
association needed to achieve this is not chosen yet. See the
[Diki contract](../contracts/diki.md).

### Concurrent capture is expected

The main list can grow through CLI capture while the workbench consumes it.
This is normal use. Consuming an entry must not overwrite unrelated words appended
concurrently. A saved browser snapshot must not be treated as a replacement for
the current source file.

The owner's answer is to remove the duplicated queue model, not choose between
synchronization modes. Processing should operate on the file-backed queue.
Detailed UI polling/notifications are not specified and are not a prerequisite
to recording this direction. Do not reopen this as a request to synchronize two
authoritative word lists.

See [ADR 0004](../decisions/0004-file-backed-word-queues.md) and task `Q-001` in
the [root to-do list](../../to-do). This change is for a separate implementation.

### Resolve words during processing; no separate batch preparation

The owner previously entered words manually, including forms that were not Diki
headwords. A separate raw/prepared-list stage resolved those forms to compatible
English entries before note creation.

That stage is deprecated. The preferred browser flow vets the current word and
offers spelling/entry choices as it is processed, rather than preparing the whole
list first. The dictionary CLI already performs lookup/selection before appending,
so CLI-captured English entries are Diki-compatible input.

This does not claim that every historical/manual/book entry is already compatible,
or establish Polish field compatibility before translations have been selected.
The current word-processing path still needs to handle unresolved source entries.
Legacy retirement is a separate `L-001` task; see the [roadmap](../roadmap.md).

### Current browser-session behavior — implementation mismatch

- `backend/app.py` reads the main text file when creating a session, then
  `SessionStore` persists its ordered words in SQLite. Subsequent reads use that
  saved queue; this is a snapshot, not a live file-backed queue.
- The add session also stores target configuration and the current draft.
- The frontend schedules ordinary draft persistence after a short debounce and
  attempts to flush it on `Exit to home`. Browser/tab-close behavior is not a
  separately established durability guarantee.
- Tag/flag review uses temporary browser state rather than persisted add-session
  state. Existing Anki notes are still saved separately through the commit path.

The copied word queue conflicts with the confirmed file-backed model. The owner
separately clarified the role of an unfinished word's draft below.

### Unfinished-word drafts: optional convenience

If the owner closes the UI before saving a word to Anki, selecting its Polish
translations again later is acceptable. Processing one word is little work, and
the owner rarely leaves in the middle of it.

Draft autosave/resume was accepted as a convenience during AI-assisted UI
development, rather than arising from a strong workflow need. Its absence would
make little difference to the owner.

Removal is a possible simplification for a later session, not a firm requirement
or an urgent correction. It is recorded as `Q-002` in [to-do](../../to-do). The
existing behavior remains until a separate implementation decision.

The pending word still belongs in the source file until it is resolved. This
answer concerns unsaved per-word UI selections, not loss of committed Anki data,
the Diki HTML/audio cache, or save verification/recovery. Persistence of other
settings is not decided by this answer; do not generalize it to all storage.

### Current book input and possible evolution

- The current book input is similar to the main list: one word or phrase per line.
- Historically, the owner manually downloaded a Kindle file and placed it
  somewhere in the repository. No fixed book-folder convention was established.
- It sometimes contains import artifacts such as quotes, apostrophes, brackets, or
  parentheses. Exact cleanup rules have not been agreed.
- The owner confirmed `"flimsy"` → `flimsy` as a representative cleanup example.
- The owner recalls writing artifact-stripping code intended to preserve meaningful
  characters. Its location and relationship to the current import path have not
  been established; that recollection is not proof of current browser behavior.
- Book import is infrequent, and its format is not considered settled. A future
  input might be JSON containing a list of words/phrases.
- JSON is a possible future format, not a requirement to implement now.
- The quote example does not establish that punctuation should always be stripped.
  Some punctuation is valid vocabulary content; broader cleanup rules remain open.

## Current implementation and evidence

| Area | Observed behavior | Evidence |
| --- | --- | --- |
| Main capture | CLI offers to append after lookup; cooperating writers share a file lock | `tools/diki_lookup.py`, `backend/word_list.py` |
| Browser import | Reads file contents, splits nonempty lines, submits words and an optional session name | `frontend/src/App.tsx`, `createImportSession` and `readImportFile` |
| Session persistence | Stores ordered words separately in SQLite; source is a string, not an established editable-file association | `backend/storage.py`, `create_add_session` |
| Verified cleanup | After Anki read-back, archives and removes matches from the configured main list | `backend/word_completion.py` |
| Resolution order | Browser service checks for an existing Anki note using the submitted word before fetching Diki HTML | `backend/services.py`, `lookup_current` |
| Diki lookup | Returns exact-headword translation groups or suggestions; does not expose a separate resolved canonical-word result | `external_APIs/dikiApi.py`, `lookup` and `parse_meanings` |
| Book lists | Text files are discovered for offline preparation without source modification | `external_APIs/diki_lists.py` |
| Generic skip | Advances the browser queue without touching the source file | `backend/services.py`, `skip_current` |

Relevant regression evidence inspected in
[`tests/test_word_completion.py`](../../tests/test_word_completion.py):

- `test_concurrent_append_waits_for_cleanup_and_is_not_lost` covers preservation of
  concurrent capture with cooperating writers.
- `test_skip_never_removes_from_source` explicitly describes current skip behavior;
  it does not establish that this behavior meets the owner's discard requirement.
- `test_legacy_cleanup_confirms_notes_and_archives_duplicates` covers a separate
  historical cleanup command, not a complete interactive already-present outcome.

Commits `7e724bc` and `6eb461a` introduced verified main-list cleanup and recorded
a subsequent cleanup operation respectively. See the
[history baseline](../review.md#repository-evidence-baseline).

## Implementation gaps and unresolved decisions

1. **Authoritative queue refactor (`Q-001`):** remove the redundant SQLite add-queue
   snapshot and use the source file directly. Record only during this walkthrough;
   implementation and retirement of old session state happen separately.
2. **Book-source consumption:** cleanup currently targets the configured main list.
   An imported book's original pending file is not consumed by that path.
3. **Source association:** browser file import sends content rather than establishing
   which source entry the backend should update. Repository-local book files are
   established practice, but an association mechanism has not been chosen. Do not
   require the owner to settle an exact folder before documenting the workflow.
4. **Per-entry resolution:** cleanup currently removes all matching normalized
   lines from the main file, independent of queue origin. That does not implement
   the desired rule of resolving the current source entry without evaluating other
   pending entries. The required occurrence/source association remains to be designed.
5. **Deliberate discard:** generic skip leaves source entries intact. That is not
   sufficient for the owner's stated decision to stop learning a pending word.
6. **Already-present completion:** define the interactive completion behavior after
   the Anki matching rules are established; do not retain known resolved entries
   merely because they were skipped in one session.
7. **Import artifacts:** `"flimsy"` → `flimsy` is confirmed, but a full punctuation
   policy is not. A targeted inspection did not identify the recalled historical
   stripping routine in the current Python sources. The current browser import
   trims whitespace rather than stripping quotes. Do not silently override the
   existing `en_word` content contract.
8. **Dictionary-informed identity:** current browser lookup checks Anki before Diki
   using the submitted word. Intended stored identity is now confirmed as the
   relevant Diki headword. Implementing this identity through selection, Anki
   checks, and original-source consumption remains open; do not confuse agreement
   on the outcome with an implemented raw-to-resolved association.
9. **Acknowledged-create completion (`S-001`):** the current verifier retains a word
   if follow-up read-back fails. The owner wants notification and continuation
   for that rare case once creation is acknowledged; implementation is deferred.

## Authority

The intended semantics above come from the owner's second through twenty-second interview
batches on 2026-11-17. Batch 3 clarifies that batch 2's already-present outcome is
per-entry, not an eager queue-cleaning policy. Batch 4 establishes the resolved
Diki headword as the intended stored English content. Batch 15 explicitly makes
the source file authoritative and defers the SQLite queue refactor as a todo.
Batch 16 confirms that redoing unsaved selections is acceptable and records draft
removal as an optional simplification. Batch 19 deprecates whole-list preparation
and confirms resolved English input from CLI capture. Batch 22 accepts completion
with a warning after acknowledged creation if follow-up confirmation fails.
Implementation observations are evidence, not newly accepted policy.
Track interview progress and remaining questions in the
[walkthrough checkpoint](../review.md).
