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
