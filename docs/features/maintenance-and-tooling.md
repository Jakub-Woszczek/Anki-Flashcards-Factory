# Maintenance, retired workflows, and quality tooling

Last updated: 2026-11-22.

Status: completed owner-approved cleanup and tooling work. These records describe
implemented changes, not pending todo items. Operational commands and ongoing
verification rules live in [development and verification](../development.md).

## Whole-list preprocessing retired (`L-001`)

Completed 2026-11-19. The older `RawNotesEditor.py` / `raw_notes/` /
`prepared_notes/` path prepared Diki-compatible English lists from manually
collected input before note creation. The owner confirmed it was deprecated:
browser processing vets each current word, while CLI capture already resolves
the Diki English entry before appending.

The owner approved removing the implementation, vocabulary directories and their
contents, `main.py --app -e`, obsolete configuration helpers, and the raw-editor
test module. Per-word browser/CLI resolution remains. See the
[Diki contract](../contracts/diki.md#resolution-belongs-to-capture-or-current-word-processing).

## Legacy-code cleanup and obsolete tests (`T-001`)

Completed 2026-11-19 in a separately authorized cleanup. The owner approved
retiring all inspected cleanup candidates:

- Whole-list preprocessing and its vocabulary directories (`L-001`).
- Manual local-index inspection, import, and deletion commands under `main.py --db`,
  including the special digit/`C2` deck filter and exclusive scan helpers.
- The uncalled `external_APIs/ankiUtils.py` inspection helpers.
- Direct-to-folder MP3 export (`diki_audio_harness`) and its dedicated tests.
- Unused fixed-model note-creation and deck-moving wrappers and their smoke tests.
- Unused redundancy/path/URL helpers, no-op index-save compatibility code, and
  stale client attributes/example data.

The browser's active local-index lookup/add/delete operations and legacy JSON
index import remain. Audio still uses the shared cache and AnkiConnect upload to
the active profile; refresh preserves original decks.

`T-001` removed the three obsolete early live smoke tests, originating in initial
commit `d301a5d` (2025-09-23):

- `TestAnkiConnect.test_add_flashcard`
- `TestAnkiConnect.test_move_note_to_deck`
- `TestRawNotesEditor.test_diki_possible_spellings`

The owner's expanded approval also retired the two read-only legacy Anki tests
with their index-scan helpers. Both legacy modules (`test_ankiConnect.py` and
`test_rawNotesEditor.py`) are gone. The two explicitly opt-in live Diki checks
remain.

Verification: full unittest discovery ran 107 tests, with 2 opt-in live Diki tests
skipped and no failures, while socket connections were blocked by a temporary
test-process guard. `python main.py --help` exposed only browser-app options.
An initial run with application-wide `DIKI_OFFLINE=1` blocked mocked downloads;
the successful run unset that override. No live Anki/Diki checks were performed.

## Enforced offline test boundary (`T-002`)

Completed 2026-11-19 during the follow-up repository/tooling cleanup.
`python -m tools.test_offline` guards discovery and tests against socket/DNS access
and forces live checks off. The shared check command, local Python hooks, and CI
use it. Dedicated regressions verify the guard. Direct unittest remains available
for explicitly requested integrations.

Routine tests use saved Diki fixtures and fake Anki responses. Real Diki/Anki
checks, including read-only collection queries, remain explicitly invoked
integration actions. See [the verification boundary](../development.md#routine-automated-tests--accepted-boundary).

## Repository hygiene and quality tooling

Completed 2026-11-19. The owner approved a behavior-preserving cleanup: move the
index into `backend/note_index.py`, normalize integration/test module names,
remove tracked IDE/macOS artifacts from Git while retaining local copies, and
simplify ignore rules. Existing launcher commands, resource directories, and
collection contracts were preserved.

Shared VS Code overrides are workspace-scoped. Pinned development tools, reviewed
lint/format/type corrections, local hooks, `python -m tools.check`, and a macOS CI
job provide repeatable verification. Detailed results and commands are recorded
in [development and verification](../development.md#project-local-quality-tooling).

## Handbook and todo organization

Completed 2026-11-22. The former root `to-do` was replaced by
[docs/todo.md](../todo.md), preserving the owner's pending loose thoughts and
optional `Q-002` idea. Entries are not specifications, confirmed diagnoses,
priorities, implementation plans, or authorization to implement.

Completed queue, headword, and save changes are linked from the
[feature map](../features.md); maintenance/tooling records were moved here from
the roadmap. The roadmap provides future-work context. The handbook index and
`AGENTS.md` establish the ongoing rule: document completion in the relevant
feature page, then remove the pending thought. Contracts and ADRs continue to
own detailed rules and decisions.

## Translation editor extraction

Completed 2026-11-22. Translation selection/editing was introduced inline in
`App.tsx` by browser-workspace commit `6437e8c`. The later Q-001 plan explicitly
preserved the owner's uncommitted `TranslationEditor` extraction; it is a
standalone frontend refactor rather than missing Q-001 functionality.

`frontend/src/TranslationEditor.tsx` now owns the meaning-group controls and local
editing state. `App.tsx` still owns the draft and existing debounced persistence:
typing updates local draft text, while selection, confirmation, reset, and custom
addition schedule persistence. Editing and custom translations remain available.
The component adds accessible input labels and disabled fieldsets, and its
current-entry key resets editing state when moving to another queue entry.

Verification: `python -m tools.check` passed Ruff lint/format, Pyright with zero
errors/warnings, 156 tests (2 opt-in live checks skipped), and frontend
TypeScript/production build. No live Anki/Diki checks were run.

## Retired standalone files

Completed 2026-11-22 at the owner's request:

- Removed root `test_words` from Git. Its three words (`sufficient`, `take`,
  `sleep in`) were input for the old functional-test launcher added in `bd9fda5`.
  That launch path was retired by browser migration `6437e8c`; no current
  source/documentation reference to the input file was found.
- Removed `tools/Templatka zdęc.xcf` from Git. It was a 1000 × 1000 RGB GIMP
  template added in `5b9c77c`, with no identified runtime references.

Both files were already absent from the working tree; this cleanup records their
deletion in version control. Historical versions remain in Git history.
