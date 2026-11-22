# Refresh existing notes through Diki selection

Last updated: 2026-11-22.

Specification status: gradual-cleanup purpose and original-deck preservation
confirmed; exact compatibility and other preservation rules are still being refined.

Implementation status: existing-note comparison and in-place update are present.
Full Diki compatibility is a goal, not a verified guarantee of the current path.

## Purpose

An encountered word may already have a manually authored Anki note. The app lets
the owner overwrite/update it during normal word processing so its Polish content
is rebuilt through the current Diki-extraction and selection workflow.

This can be valuable even when the selected translations appear unchanged. The
objective is **predictable, Diki-compatible stored content**, not necessarily a
visible change in meaning.

The owner introduced this as a gradual way to clean manually authored notes with
translation artifacts. A future collection-wide cleanup might eventually reduce
or remove the need for this opportunistic refresh feature. That is a possible
future outcome, not a decision to deprecate it now. Before planning broad cleanup,
the owner wants structured target data contracts that define what to migrate to.
See [the contract-first cleanup discussion](../roadmap.md#future-discussion-contract-first-cleanup-of-older-notes).

## Intended outcome

- The relevant Diki English headword is the intended stored English identity.
- The owner selects Polish translation strings from Diki's grouped alternatives.
- Stored Polish content should support later comparison with the extracted strings
  to identify what text was selected. Recovering its original sense group is not
  required, even where the same text appears in multiple groups.
- Refreshing an existing note is part of the normal vocabulary-processing
  capability; it is not limited to a separate repair session.
- Selection is the owner's judgment. No automatic overwrite of every existing
  note or bulk conversion policy was requested.
- Refreshing an existing note preserves its cards' current decks. The selected
  queue target controls new-note placement, not relocation of refreshed notes.
- Notes moved by the earlier behavior may remain where they are. The owner asked
  for a prospective correction, not a historical deck-restoration operation.

See the [Diki compatibility contract](../contracts/diki.md) for the English/Polish
distinction and the tentative selection-only direction. The owner is considering
removing edits/custom additions but has not made that decision; the UI stays as is.

## Current behavior and evidence

- `frontend/src/App.tsx` displays an existing note and compares current/proposed
  fields. **Update and continue** updates it in place; **Discard from queue**
  consumes an already-covered pending entry while leaving Anki unchanged.
  Duplicate-note deletion/recreation was retired in Q-001.
- Diki headword resolution now precedes Anki matching, with exact-case preference
  and case-distinct candidate validation. See [ADR 0005](../decisions/0005-diki-headwords-and-case.md).
  This does not remove the existing English-field lock or rewrite historical casing.
- `backend/services.py` constructs translation HTML from selected draft values
  and writes updates against the existing note ID. The normal update path locks
  the English field and rejects note-type changes.
- Existing audio is preserved on an update if refreshed audio is unavailable.
- Updates preserve each card's pre-update deck, including siblings in different
  decks. The original card/deck mapping is recorded in the save journal and checked
  during read-back and recovery instead of verifying the queue's target deck.
- The verified-save path reads resulting fields back before consuming the exact
  original source entry. Tag/flag review has no pending source to consume.

These are inspected implementation properties, not a completed specification of
everything an update may alter. In particular, the English-field lock means that
refreshing Polish content is not itself an implementation of correcting every
non-Diki-compatible historical English headword.

## Gaps and later decisions

- Settle the precise Polish compatibility/encoding rules before claiming every
  update produces recoverable source selections.
- Settle edit/custom-translation behavior when the owner is ready. Source-group
  identity is already confirmed unnecessary and is not a remaining blocker.
- Deck preservation is settled and implemented. A detailed policy for other
  fields/tags and learned-card state remains separate; the owner's latest answer
  explained the cleanup purpose rather than enumerating all preservation rules.

## Alternative-headword matching

Implemented 2026-11-22 following the owner's `anesthetic`/`anaesthetic` report.
[ADR 0008](../decisions/0008-diki-entry-alternatives-and-existing-notes.md) records
the motivating screenshot/text, retained-source provenance, and confirmed rules.

`EntrySelection`/`DikiLookup` now carry `matching_headwords`: genuine headwords
from the selected English→Polish entry in source order, with case-sensitivity
metadata for each alternative. This is independent of the resolved spelling and
the full-entry chooser. `FactoryService` searches these alternatives in order,
validating actual Anki English fields and advisory index candidates. The first
valid matching spelling wins. Failed alias searches produce an error rather than
silently reporting a new word. Existing duplicate-note handling stays manual.

Browser responses/drafts carry `matchingHeadwords`, and the existing-note banner
shows a differing stored English spelling. Preview and comparison use the locked
existing English value. Save rederives identity from the retained Diki response,
checks the existing note again before update, and preserves the English field,
note type, deck mappings, and fallback audio. This applies to add processing and
stateless review. A creation recheck prevents adding another variant when an
existing note appeared since lookup. Custom-card creation retains its own rules.

Alternative-aware intents bind the existing note ID and verified headword set.
Read-back/recovery still compare the preserved English field exactly. Confirmed
index writes use the actual stored spelling, rather than creating mismatched
lookup-alias keys. No database schema migration is required.

On reopening a resolved add draft that lacks `matchingHeadwords`, the browser
requests a preserving lookup. The backend reuses its stored query/headword and
retains selections, tags, flag, and target override while replacing matching
metadata. Translation selections are not reset by this upgrade.

The controlled `anaesthetic-variants.html` fixture preserves the observed headword
order and both meanings. Offline regressions cover ordered matching/fallback,
actual field validation, per-alternative meaningful case, preserving refresh and
preview, original-occurrence consumption, consistent index reload, legacy drafts,
client-tampering rejection, late-arriving existing notes, and refresh recovery.
See [development verification](../development.md).

## Verification of the deck-preservation correction

On 2026-11-17, five regression tests reproduced the previous behavior before the
fix. The corrected path passed 65 isolated tests covering word completion,
targeting, stateless review, offline resources, audio, and sync throttling.
The code and regression tests were committed separately as `60cdb9f` (`Preserve
existing card decks when refreshing Anki notes`); handbook/README edits were not
included in that commit.

The regressions cover original-deck retention, sibling cards in different decks,
recovery against the persisted deck snapshot after a mismatch, missing card-deck
data, and updates through review. Tests use in-memory Anki fakes and temporary
files/databases; no live collection was updated or historical notes relocated.

## Authority

The owner explained this feature's objective in batch 8, refined compatibility in
batch 9, and confirmed deck preservation and its gradual-cleanup role in batch 10
on 2026-11-17. Batch 10 explicitly requested the prospective behavior correction.
Progress and next questions are in [the walkthrough checkpoint](../review.md).
