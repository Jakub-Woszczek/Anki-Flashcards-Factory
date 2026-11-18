# Review notes marked during study

Last updated: 2026-11-17.

Specification status: flag purpose and lack of a red/orange distinction confirmed;
precise review-completion mechanics are not yet specified.

Implementation status: the Factory provides tag/flag inventory, deck-scoped
selection, and a temporary existing-note review workspace.

## Problem and purpose

While studying in Anki on a phone or laptop, the owner may encounter an older
card that seemed fine when created but now needs attention. A flag is an easy
way to defer that attention until later without interrupting the study session.

The later action is a human decision: the content may need editing, something
may need deleting, or the note may need reconsideration. The flag itself does
not identify a specific defect or prescribe one automatic repair.

This explains the purpose of a workflow for revisiting marked existing notes.
It is broader than refreshing Polish content solely for Diki compatibility.

## Confirmed flag semantics

- Flags are primarily set during study, not during note creation.
- Red and orange have the same practical meaning: **something to attend to later**.
- No meaningful severity, issue-type, or processing-stage distinction between
  those two colors was established.
- Do not infer a red-to-orange state machine or different automatic actions from
  the colors. The owner chooses what to do when examining the item.
- Anki stores flags on cards, even though the owner naturally describes marking
  a note. Editing note fields and changing a card flag remain distinct operations.

Study on a phone is part of the Anki workflow. The Factory's confirmed operating
scope remains the local workbench on the owner's Mac.

## Related tags

`GEMINI_DIFF` separately marks a discrepancy for manual examination after
addition. `TO_EDIT` and `ERROR` are historical workarounds, not the current primary
reason for flag-based attention. `IMAGE` is a candidate marker for a deferred
feature. See [Anki tag/flag rules](../contracts/anki.md).

## Current implementation evidence

- The homepage exposes **Review tags and flags**, with an optional deck scope.
- `FactoryService.review_inventory` reads current Anki tags and flag counts.
- Tag snapshots contain note IDs; flag snapshots retain the selected card IDs
  with their note IDs.
- The browser uses a temporary review traversal and an existing-note editor;
  it is separate from pending vocabulary files.
- Field updates use the shared save path, including the corrected preservation
  of existing decks.

Read-only inspection within `English` and subdecks found 10 red cards, 111 orange
cards, and 46 `GEMINI_DIFF` notes. These are historical snapshot counts, not fixed
workloads or priorities.

The owner has not defined exact completion/flag-clearing behavior in this batch.
No new automation, UI changes, flag changes, or content cleanup was requested.

## Authority

Purpose comes from interview batch 18 on 2026-11-17. Implementation facts come
from code and earlier read-only Anki queries. No collection state was changed
while documenting this explanation.
