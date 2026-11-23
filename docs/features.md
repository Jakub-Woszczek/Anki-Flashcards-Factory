# Feature map and specification coverage

Last updated: 2026-11-23.

This is a living capability inventory. "Present" means observed in code or live
Anki where noted, not that every path meets its intended contract or was freshly
tested. Specification status and implementation status are separate.

| Capability | Purpose / owner intent | Implementation and specification state |
| --- | --- | --- |
| Dictionary CLI and capture | Resolve the Diki English entry, show usage examples, and append chosen vocabulary | Present; browser/CLI now preserve resolved headword casing and distinguish case-specific meanings. [ADR 0005](decisions/0005-diki-headwords-and-case.md). Source: `tools/diki_lookup.py` |
| Word intake and processing | Consume main/book files as pending queues | `Q-001` implemented: discover/open live files, consume exact current occurrences, preserve concurrent capture and recover interrupted removals. Upload/paste, queue editing/creation/deletion retired. [Rules](features/vocabulary-queues.md) |
| Translation curation | Choose a diverse, useful set of Diki translation strings | Present; human selection confirmed. Editing/custom additions present, possible selection-only direction not final. [Diki contract](contracts/diki.md) |
| Diki result recognition | Distinguish English→Polish entries, choices, collocations, and missing/unknown results | Shared structural detection, separate spelling/related/headword choices, offline selected-entry reuse, and durable unknown-layout diagnostics. [Feature](features/diki-results.md), [ADR 0007](decisions/0007-diki-result-recognition.md) |
| Anki target selection | Select deck, note type, and field mapping for creation | Present; default type and historical deck context confirmed. [Anki contract](contracts/anki.md) |
| Existing-note refresh | Gradually clean older manual translations through deterministic Diki selection | Present; selected-entry alternative headwords find existing notes while preserving their English spelling and decks. [Feature](features/existing-note-refresh.md), [ADR 0008](decisions/0008-diki-entry-alternatives-and-existing-notes.md) |
| Save completion and recovery | Complete processed entries with useful feedback | `S-001` implemented: acknowledged creation with unavailable confirmation warns precisely and advances; actual mismatches/updates remain strict. Local source-removal failure has an explicit restart-safe retry |
| Tag/flag review | Revisit items marked during study for later editing, deleting, or reconsideration | Present; red/orange both mean attention needed. Exact completion behavior remains open. [Feature](features/marked-note-review.md) |
| LLM assistance | Quickly understand words and disparate Polish alternatives | Present via optional Gemini integration; purpose confirmed. [Feature](features/llm-assistance.md) |
| Resource cache and prefetch | Offline additions plus reusable source data for old-note checks | Shared retained HTML/audio plus automatic 100-entry-per-file remote preparation and one-time existing-note HTML inventory. Population/worker rollout is separate. [Feature](features/offline-cache.md) |
| Remote dictionary preparation | Fetch while the Mac sleeps and import completed work in background | Priority buffers/coverage, one finite startup drain with immediate import/ACK, asynchronous replenishment, and recovery. Original manual path verified live; updated worker required for scheduling. [Feature](features/remote-downloads.md) |
| Node connection status | See whether the remote API is reachable and authenticated | Header status button checks on appearance/click, with independent short-timeout status requests and no dictionary fetching. [Details](features/remote-downloads.md#node-connection-indicator) |
| Separate code/data storage | Keep mutable vocabulary, resources, and recovery data out of code commits | Implemented: one required `ANKI_FACTORY_DATA_DIR`; durable data including HTML/MP3 and SQLite is versioned separately. [Layout and migration](features/data-storage.md) |
| Pronunciation audio | Obtain relevant-word audio; either dialect acceptable | Present. British-first is historical fallback, not a hard preference. [Diki contract](contracts/diki.md#pronunciation-audio) |
| Field-contract audit | Incrementally establish predictable stored content for future refinement | Present; only `en_word` syntax currently defined/audited. [Field contracts](../note-data-contracts.md) |
| Image candidate marking | Mark words that might later suit image cards | Present as `IMAGE`; partial evaluation coverage. Full authoring/migration is deferred |
| Per-word draft recovery | Convenience when leaving before completing one word | Present but rarely useful; redoing selections is acceptable. Optional simplification `Q-002` |
| Older raw/prepared-file preprocessing | Formerly prepare whole Diki-compatible English lists before note creation | Retired 2026-11-19 (`L-001`): code, CLI option, tests, and vocabulary directories removed. Per-word browser/CLI resolution remains |
| Maintenance and quality tooling | Retire obsolete paths and keep local checks repeatable and offline | Completed legacy cleanup (`L-001`/`T-001`), guarded runner (`T-002`), repository hygiene, hooks, and macOS CI. [Details](features/maintenance-and-tooling.md) |

## Deferred features and open decisions

The [roadmap](roadmap.md) records broader old-note cleanup, image-note workflows,
sentences on notes, newer definition/LLM ideas, and the tentative selection-only
translation direction. They are not automatically accepted implementation tasks.
The owner's loose thoughts are in [todo.md](todo.md); they are not specifications,
priorities, implementation plans, or authorization to implement.

## Completed development and evidence

Completed items leave the todo list and are documented with the relevant feature.
Contracts and ADRs retain ownership of detailed rules and decisions.

| Completed | Change | Documentation |
| --- | --- | --- |
| 2026-11-23 | Added the header Node health/check button beside Anki and Gemini | [Node connection indicator](features/remote-downloads.md#node-connection-indicator) |
| 2026-11-23 | Implemented automatic 100-entry buffers, resource-aware priority scheduling, one-time HTML inventory, and one startup drain with immediate import/ACK | [Remote scheduling](features/remote-downloads.md#automatic-scheduling--2026-11-23), [ADR 0009](decisions/0009-remote-preparation-scheduling.md) |
| 2026-11-22 | Restored and ported the stashed Northflank downloader to current imports, paths, and dictionary recognition while retaining queue/transfer behavior | [Remote downloader](features/remote-downloads.md) |
| 2026-11-22 | Matched existing notes by genuine Diki alternatives, based on the anesthetic/anaesthetic case; preserved spelling, selections, and refresh verification | [Existing-note alternatives](features/existing-note-refresh.md#alternative-headword-matching), [ADR 0008](decisions/0008-diki-entry-alternatives-and-existing-notes.md) |
| 2026-11-22 | Added shared Diki result detection, distinct related/headword choices, and unknown-layout diagnostics | [Diki result recognition](features/diki-results.md) |
| 2026-11-22 | Repaired the stale local `diki` shell launcher and moved virtualenv entry points; audited checkout-dependent integrations | [Checkout relocation](features/maintenance-and-tooling.md#checkout-relocation-and-shell-launchers) |
| 2026-11-22 | Separated and migrated durable data, centralized paths, retired deprecated temporary audio, and regenerated scheduler configuration | [Data storage](features/data-storage.md), [ADR 0006](decisions/0006-separate-data-root.md) |
| 2026-11-19 | Retired whole-list preprocessing (`L-001`), obsolete live tests (`T-001`), and other approved legacy paths | [Maintenance and retired workflows](features/maintenance-and-tooling.md) |
| 2026-11-19 | Enforced offline checks (`T-002`) and added repository quality tooling | [Tooling feature](features/maintenance-and-tooling.md#enforced-offline-test-boundary-t-002), [verification guide](development.md) |
| 2026-11-21 | Live source queues (`Q-001`), source-only discard, and existing-note UX simplification | [Vocabulary queues](features/vocabulary-queues.md) |
| 2026-11-21 | Fixed Basel/lead-astray resolution and preserved meaningful casing | [Diki contract](contracts/diki.md#resolution-and-case--accepted-2026-11-21), [ADR 0005](decisions/0005-diki-headwords-and-case.md) |
| 2026-11-21 | Continued after acknowledged creation with unavailable confirmation (`S-001`), with local-only queue-removal retry | [Save completion](contracts/anki.md#acknowledged-creation-with-failed-follow-up-confirmation), [queue workflow](features/vocabulary-queues.md#save-confirmation) |
| 2026-11-22 | Separated loose todo thoughts from completed feature records and established documentation ownership rules | [Handbook organization](features/maintenance-and-tooling.md#handbook-and-todo-organization) |
| 2026-11-22 | Extracted the translation editor from the workspace, retaining editing/custom translations and draft persistence | [Frontend refactor](features/maintenance-and-tooling.md#translation-editor-extraction) |
| 2026-11-22 | Removed orphaned functional-test input and the standalone GIMP template from Git | [Retired files](features/maintenance-and-tooling.md#retired-standalone-files) |

On 2026-11-21, `Q-001` replaced SQLite word snapshots with live source queues.
Discard replaces skip/keep-existing; duplicate-note deletion was retired in favor
of update-in-place. The owner-approved 25 SQLite-only entries were appended to
the main file before local queue migration. See [queue evidence](features/vocabulary-queues.md#migration-and-verification-evidence).

Recent milestones and commits are in the
[history baseline](review.md#repository-evidence-baseline). They include browser/
SQLite migration, examples, offline prefetch, fetching isolation, incremental
contracts, verified source cleanup, and the deck-preservation correction.

Historical data operations are identified separately from software features.
The [2026-11-19 cleanup](features/maintenance-and-tooling.md#legacy-code-cleanup-and-obsolete-tests-t-001)
also retired manual index-maintenance commands, standalone inspection helpers,
direct-folder audio export, unused Anki wrappers, and their obsolete tests.
Existing code and past plans remain evidence rather than automatic approval of
desired behavior. For remaining coverage/questions, use [review.md](review.md).
