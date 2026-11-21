# ADR 0002: Per-entry vocabulary resolution

Date: 2026-11-17.

Status: Accepted — stated by the owner in the vocabulary-source follow-up.

## Context

Pending vocabulary may contain different forms of a word across or within lists.
The owner's example is queued `causes` versus Diki's `cause` entry. Raw spelling
does not provide enough information to safely decide that all such entries are
redundant. The owner evaluates the dictionary entry and Anki content when working
on each queued word.

## Decision

Resolve vocabulary when its entry is taken for processing. Processing one entry
must not trigger opportunistic evaluation or removal of other pending entries,
whether in the same list or another list.

Use Diki's representation of the current word to inform redundancy evaluation.
Do not introduce automatic cross-queue variant matching or stemming-based cleanup
as an assumed requirement; that is not a current project goal.

## Rationale and trade-offs

- The owner considers automatic equivalence decisions unsafe without evaluation.
- A dictionary lookup can clarify the relevant headword in a way that comparing
  raw queue strings cannot.
- Other entries may remain pending even when their eventual resolution will be
  "already in Anki". They will be evaluated at their own turn.
- This favors explicit per-entry decisions over eagerly shrinking all queues.

## Consequences and open details

- Distinguish the original queued text from the resolved dictionary word.
- Track enough source association to consume the current entry rather than
  treating a save as permission to remove all matching queued lines.
- Headword-selection and case-aware Anki candidate matching were subsequently
  specified and implemented in [ADR 0005](0005-diki-headwords-and-case.md).
  Raw-to-resolved source bookkeeping was implemented in Q-001 using
  current-entry IDs, source fingerprints, and exact-line consumption with receipts.
- Historical bulk cleanup commits remain historical operations; they do not define
  the desired normal interactive workflow.

See [vocabulary queue rules](../features/vocabulary-queues.md) and the
[walkthrough checkpoint](../review.md).

Follow-up clarification in interview batch 4: the intended stored English form is
the relevant Diki headword, termed **Diki compatibility**. This resolves the stored
form question without choosing the low-level source-association mechanism. See
the [Diki contract](../contracts/diki.md).

Supersedes: none. Clarifies the earlier queue discussion's already-in-Anki outcome.
Superseded by: none.
