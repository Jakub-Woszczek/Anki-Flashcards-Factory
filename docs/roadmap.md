# Future work and deferred discussions

Last updated: 2026-11-17.

This is a small record of future work explicitly mentioned by the owner during
the handbook walkthrough. Entries are not an implementation authorization or an
ordered delivery schedule. Current intent is documented in the linked contracts;
walkthrough progress lives in [review.md](review.md).

Behavior changes requested during the walkthrough are recorded in the root
[to-do list](../to-do) for a separate implementation session. This roadmap supplies
context and deferred feature ideas; it is not permission to implement them here.

## Recorded change: use source files as the only word queues (`Q-001`)

The owner explicitly wants `words_to_add/words_to_add.txt` itself to be the queue.
The current persisted SQLite copy adds unnecessary state and synchronization.

Todo: replace the duplicated add-queue/snapshot model with file-backed processing
and consumption. The source-file lifecycle and concurrent CLI capture still apply.
Per-word draft recovery is optional as described below. Settings persistence is
separate; removing unrelated SQLite indexes or journals is not requested.

Status: accepted direction, not implemented; tracked as `Q-001` in [to-do](../to-do).
See [ADR 0004](decisions/0004-file-backed-word-queues.md) and
[vocabulary queue rules](features/vocabulary-queues.md).

## Optional simplification: remove unfinished-word drafts (`Q-002`)

The owner rarely interrupts processing a word, and re-selecting unsaved
translations is little effort. Draft autosave/resume is a rarely used convenience
with little effect on the core workflow.

Status: possible simplification, not a firm removal requirement. Record for the
later queue/UI refactor; leave the current behavior in place during this
walkthrough. Task `Q-002` in [to-do](../to-do) captures the candidate.

This concerns per-word UI drafts, not the reusable Diki cache or durable save
verification/recovery records. See
[draft expectations](features/vocabulary-queues.md#unfinished-word-drafts-optional-convenience).

## Deprecated workflow: whole-list word preprocessing (`L-001`)

The older `RawNotesEditor.py` / `raw_notes/` / `prepared_notes/` path prepared
Diki-compatible English word lists from manually collected, non-compatible input
before the main note-creation stage.

The owner confirms that this workflow is deprecated. The browser now vets each
word during processing, including possible-spelling choices, which is preferred
over vetting an entire list in advance. CLI capture already resolves the English
entry before appending it, so captured words are Diki-compatible input.

Status: deprecated, pending a separate retirement review recorded as `L-001` in
[to-do](../to-do). Legacy code, entry points, files, and references remain in the
repository during this documentation walkthrough. No deletion/data migration is
being performed here.

## Obsolete initial live tests (`T-001`)

The owner confirmed that the three live methods discussed during test provenance
research were early attempts to test the initial application and may be deleted:

- `TestAnkiConnect.test_add_flashcard`
- `TestAnkiConnect.test_move_note_to_deck`
- `TestRawNotesEditor.test_diki_possible_spellings`

They originate in initial commit `d301a5d` (2025-09-23), before the later test
organization. Record their deletion as `T-001` in [to-do](../to-do), for a separate
cleanup session under the documentation-only walkthrough rule. This is permission
to retire these three methods, not a request to delete all integration tests or
the remaining read-only Anki inspection methods.

Status: owner-approved retirement, not implemented. The broader test boundary is
now accepted and separately tracked as `T-002` below.

## Test boundary enforcement (`T-002`)

Accepted rule: routine automated tests run offline against saved Diki fixtures
and fake Anki responses. Real Diki/Anki checks, including read-only collection
queries, must be explicitly invoked integration checks.

Current test organization does not yet enforce that boundary for all discovery.
Status: confirmed rule with implementation work recorded as `T-002` in
[to-do](../to-do), to be implemented separately. Retiring the three original smoke
methods (`T-001`) and handling the remaining live readers are distinct scopes.
See [development and verification](development.md).

## Simplify failed confirmation after acknowledged creation (`S-001`)

The owner considers the discussed case of Anki creating a note and the follow-up
confirmation request failing too rare to justify blocking their workflow.

Intended behavior: notify that creation succeeded but confirmation failed, then
continue normally. Treat acknowledgement as sufficient completion in that case.
The current strict read-back/recovery path is not the desired user experience
for this scenario.

Status: accepted simplification, recorded as `S-001` in [to-do](../to-do) for a
separate implementation session. See
[Anki completion semantics](contracts/anki.md#acknowledged-creation-with-failed-follow-up-confirmation).
This does not specify every unacknowledged write/error outcome or request removal
of all operation records.

## Future discussion: contract-first cleanup of older notes

The owner has plans in mind to improve the manually authored portion of the
collection, potentially hundreds or thousands of notes with translation artifacts.
A possible future cleanup would examine English words and match existing Polish
content with artifacts to appropriate Diki-extracted translation strings.

Prerequisite: define structured target data contracts so there is a clear format
to migrate to. This is a motivation for the current handbook/contract work and
the existing incremental [note contracts](../note-data-contracts.md).

Status: future feature discussion; no bulk cleanup, matching algorithm, migration,
or automatic rewrite has been specified or authorized. The current per-word
refresh feature is a gradual cleanup aid and might become less necessary after
a successful broader cleanup. Its eventual removal is not decided.

The deck-preservation bug found during this walkthrough was corrected in code/test
commit `60cdb9f` for future updates. Historical deck moves are accepted as-is and
are not a restoration task within this cleanup idea.

## Future discussion: word definitions and LLM ideas

The original LLM integration helps the owner quickly understand an English word
and reconcile diverse Polish meanings. The owner has newer ideas involving word
definitions, but explicitly deferred their explanation and design.

Status: future discussion only. No definition field, generation format, prompt
redesign, persistence, or provider expansion has been specified. See the
[LLM assistance purpose](features/llm-assistance.md).

## Coverage goal: dictionary data for existing Anki vocabulary

The owner's cache goal includes gradually collecting reusable HTML for words
already stored in Anki, so future compatibility checks and refinements do not
re-download the same source on each run.

Current prefetch discovers pending/book text lists. Existing-note words can be
cached indirectly, but a direct inventory-to-preparation mechanism and its scope
have not been selected. Priority is now established in principle: roughly the
first 100 main-queue words first, a similar book buffer, then existing-note HTML.
The owner accepts a retained rolling snapshot without routine refresh.

Status: confirmed goal/policy with an implementation gap. Exact buffer/book scope
and population mechanics remain for design; 100 is an illustrative starting target.
See [cache goals and coverage](features/offline-cache.md).

## Future discussion: example sentences in Anki notes

The owner added example extraction to see word usage during CLI lookup. There
are also plans to include examples in finished Anki notes, but the owner explicitly
identifies this as a whole feature for another session.

Status: deferred. The existing parser, CLI output, and Anki `sentences` hint are
building blocks, not a complete authoring/storage design. Do not infer sentence
selection, generation, automatic insertion, migration, or field contracts yet.
See [current example purpose](contracts/diki.md#example-sentences).

## Substantial feature to discuss later: image-note workflow

Source: owner's explanation of default note types and candidate marking in
interview batch 7.

The owner has ideas for two related capabilities:

- Migrating existing notes to an image-based note type.
- Creating image-type notes during the main word-processing workflow.

Current building blocks exist: the image note type/template and the `IMAGE`
candidate tag. The owner started evaluating candidates only partway through the
collection's history. An untagged note has not necessarily been evaluated.

Status: **deferred for its own feature discussion**. Do not drill into migration,
image sourcing, generation, or authoring choices during the current core-workflow
interview. Do not infer an automatic-conversion design from the candidate tag.

See [default note workflow and image candidates](contracts/anki.md#default-note-workflow-and-image-candidates).

## Open decision: selection-only Polish translations

The owner rarely uses text editing in the new translation UI and is leaning
toward only selecting original extracted Diki strings, eventually removing
editing/custom additions from the normal workflow to support Polish compatibility.

Status: **tentative; owner needs time to think**. This is not an accepted removal
requirement or an implementation task. Retain the current UI and return to the
decision later. See [the Diki contract](contracts/diki.md#tentative-direction-selection-only-translations).

## Low-priority convenience: alternate-headword chooser

When Diki presents several genuine headwords for the relevant entry, any of them
is acceptable. The owner considers a chooser nice to have, with low importance.

Status: optional improvement; not a prerequisite for Diki compatibility.
See [multiple genuine headwords](contracts/diki.md#multiple-genuine-headwords).

## Specification-to-implementation gaps

Known differences such as original-source consumption, deliberate discard, and
dictionary-headword identity are recorded beside their rules in
[vocabulary queues](features/vocabulary-queues.md#implementation-gaps-and-unresolved-decisions)
and the [Diki contract](contracts/diki.md#implementation-evidence-and-gaps).
They have not been prioritized into an implementation plan during this walkthrough.

## Parked historical content

Mixed image/substitution formats in `English::Diki_missing` are background evidence,
not an active cleanup project. The owner explicitly asked to keep those details
off the main walkthrough's path. Do not convert them into feature requirements
or prioritized fixes without a future request.
