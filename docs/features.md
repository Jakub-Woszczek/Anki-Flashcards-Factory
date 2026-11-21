# Feature map and specification coverage

Last updated: 2026-11-21.

This is a living capability inventory. "Present" means observed in code or live
Anki where noted, not that every path meets its intended contract or was freshly
tested. Specification status and implementation status are separate.

| Capability | Purpose / owner intent | Implementation and specification state |
| --- | --- | --- |
| Dictionary CLI and capture | Resolve the Diki English entry, show usage examples, and append chosen vocabulary | Present; captured English words are Diki-compatible input. Source: `tools/diki_lookup.py` |
| Word intake and processing | Consume main/book files as pending queues | `Q-001` implemented: discover/open live files, consume exact current occurrences, preserve concurrent capture and recover interrupted removals. Upload/paste, queue editing/creation/deletion retired. [Rules](features/vocabulary-queues.md) |
| Translation curation | Choose a diverse, useful set of Diki translation strings | Present; human selection confirmed. Editing/custom additions present, possible selection-only direction not final. [Diki contract](contracts/diki.md) |
| Anki target selection | Select deck, note type, and field mapping for creation | Present; default type and historical deck context confirmed. [Anki contract](contracts/anki.md) |
| Existing-note refresh | Gradually clean older manual translations through deterministic Diki selection | Present; purpose confirmed. Original-deck preservation fixed in `60cdb9f`. [Feature](features/existing-note-refresh.md) |
| Save completion and recovery | Complete processed entries with useful feedback | Current strict verification/recovery is present; the owner wants warning-and-continue after acknowledged creation if follow-up confirmation fails (`S-001`). Other failure rules remain limited to documented intent |
| Tag/flag review | Revisit items marked during study for later editing, deleting, or reconsideration | Present; red/orange both mean attention needed. Exact completion behavior remains open. [Feature](features/marked-note-review.md) |
| LLM assistance | Quickly understand words and disparate Polish alternatives | Present via optional Gemini integration; purpose confirmed. [Feature](features/llm-assistance.md) |
| Resource cache and prefetch | Offline additions plus reusable source data for old-note checks | Present, list-driven. Two goals and snapshot policy confirmed; existing-note coverage/buffer planner remains a gap. [Feature](features/offline-cache.md) |
| Pronunciation audio | Obtain relevant-word audio; either dialect acceptable | Present. British-first is historical fallback, not a hard preference. [Diki contract](contracts/diki.md#pronunciation-audio) |
| Field-contract audit | Incrementally establish predictable stored content for future refinement | Present; only `en_word` syntax currently defined/audited. [Field contracts](../note-data-contracts.md) |
| Image candidate marking | Mark words that might later suit image cards | Present as `IMAGE`; partial evaluation coverage. Full authoring/migration is deferred |
| Per-word draft recovery | Convenience when leaving before completing one word | Present but rarely useful; redoing selections is acceptable. Optional simplification `Q-002` |
| Older raw/prepared-file preprocessing | Formerly prepare whole Diki-compatible English lists before note creation | Retired 2026-11-19 (`L-001`): code, CLI option, tests, and vocabulary directories removed. Per-word browser/CLI resolution remains |

## Deferred features and open decisions

The [roadmap](roadmap.md) records broader old-note cleanup, image-note workflows,
sentences on notes, newer definition/LLM ideas, and the tentative selection-only
translation direction. They are not automatically accepted implementation tasks.
Concrete requested changes are in [to-do](../to-do).

## Completed development and evidence

On 2026-11-21, `Q-001` replaced SQLite word snapshots with live source queues.
Discard replaces skip/keep-existing; duplicate-note deletion was retired in favor
of update-in-place. The owner-approved 25 SQLite-only entries were appended to
the main file before local queue migration. See [queue evidence](features/vocabulary-queues.md#migration-and-verification-evidence).

Recent milestones and commits are in the
[history baseline](review.md#repository-evidence-baseline). They include browser/
SQLite migration, examples, offline prefetch, fetching isolation, incremental
contracts, verified source cleanup, and the deck-preservation correction.

Historical data operations are identified separately from software features.
The [2026-11-19 cleanup](roadmap.md#completed-legacy-code-cleanup-2026-11-19)
also retired manual index-maintenance commands, standalone inspection helpers,
direct-folder audio export, unused Anki wrappers, and their obsolete tests.
Existing code and past plans remain evidence rather than automatic approval of
desired behavior. For remaining coverage/questions, use [review.md](review.md).
