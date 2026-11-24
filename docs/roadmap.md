# Future work and deferred discussions

Last updated: 2026-11-22.

This is a small record of future work explicitly mentioned by the owner during
the handbook walkthrough. Entries are not an implementation authorization or an
ordered delivery schedule. Current intent is documented in the linked contracts;
walkthrough progress lives in [review.md](review.md).

The owner's informal reminders live in [Loose thoughts and possible work](todo.md).
They are not specifications, priorities, implementation plans, or authorization
to implement. This roadmap provides broader context for future discussions.
Implemented work belongs in the [feature documentation](features.md), including
[file-backed queues (`Q-001`)](features/vocabulary-queues.md),
[save confirmation (`S-001`)](contracts/anki.md#acknowledged-creation-with-failed-follow-up-confirmation),
and [maintenance/tooling (`L-001`, `T-001`, `T-002`)](features/maintenance-and-tooling.md).

## Optional simplification: remove unfinished-word drafts (`Q-002`)

The owner rarely interrupts processing a word, and re-selecting unsaved
translations is little effort. Draft autosave/resume is a rarely used convenience
with little effect on the core workflow.

Status: possible simplification, not a firm removal requirement. The Q-001 refactor
retained entry-bound drafts; `Q-002` remains an optional thought in [todo.md](todo.md).

This concerns per-word UI drafts, not the reusable Diki cache or durable save
verification/recovery records. See
[draft expectations](features/vocabulary-queues.md#unfinished-word-drafts).

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

Implemented locally on 2026-11-23: an explicit one-time normal-note word inventory,
missing-HTML coverage jobs below recurring first-100-entry windows in every source,
and automatic startup transfers with immediate background cache import/ACK.
Existing retained HTML is reused. Full corpus population remains an operational
goal, not a claim of completed coverage; updated worker deployment and a successful
inventory export/reconciliation are needed. Since 2026-11-24, saved-first strict
HTML statistics and a manual-review list are implemented, followed by one
background Anki/inventory/index comparison per launch. See
[strict HTML coverage](features/offline-cache.md#strict-coverage-for-existing-anki-notes),
[remote scheduling](features/remote-downloads.md)
and [ADR 0009](decisions/0009-remote-preparation-scheduling.md).

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

Original-source consumption and deliberate discard were implemented in Q-001.
Dictionary-headword-first matching and case-preserving resolution were subsequently
implemented on 2026-11-21 after the Basel/lead-astray investigation; see
[ADR 0005](decisions/0005-diki-headwords-and-case.md). Remaining import-artifact
rules and Polish compatibility details are recorded beside their rules in
[vocabulary queues](features/vocabulary-queues.md#book-content-and-remaining-decisions)
and the [Diki contract](contracts/diki.md#implementation-evidence-and-gaps).
They have not been prioritized into an implementation plan during this walkthrough.

## Parked historical content

Mixed image/substitution formats in `English::Diki_missing` are background evidence,
not an active cleanup project. The owner explicitly asked to keep those details
off the main walkthrough's path. Do not convert them into feature requirements
or prioritized fixes without a future request.
