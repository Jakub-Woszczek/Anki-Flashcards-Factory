# Architecture and operating constraints

Last updated: 2026-11-21.

Status: owner-confirmed deployment/scope and state-ownership decisions, with a
source-inspected component map. This is not a claim that every path has been
runtime-verified or that current code fully implements the intended model.

## Operating target — confirmed

- Personal workbench running on the owner's **Mac**.
- Backend, CLI tools, browser UI, and Anki operate on that same machine.
- Browser access is local; this is the intended continuing setup, not just the
  machine used during development.
- The current backend default is `127.0.0.1:8000`; AnkiConnect defaults to
  `127.0.0.1:8765`. macOS launchd supports background preparation.
- A standalone production service, remote browser workflow, or additional
  operating-system support is not part of the current required scope.

The owner confirmed this setup in interview batch 17. See
[project scope](project.md) and [ADR 0001](decisions/0001-personal-workbench-scope.md).
Anki study may also happen on a phone or laptop, where flags mark items for later
attention. The Factory itself remains the local Mac workbench.

## Components and interfaces — current implementation

```text
Owner's Mac
  Local browser → FastAPI backend → FactoryService
                                      ├─ AnkiConnect → local Anki
                                      ├─ Diki provider → shared HTML/MP3 cache
                                      ├─ optional Gemini client
                                      └─ local SQLite state/journals

  Dictionary CLI → Diki provider; appends chosen words to the main word file
  launchd → prefetch CLI → word lists → Diki provider/cache

External connections
  Diki provider → Diki when a download is needed and allowed
  Gemini client → model service when assistance is invoked/configured
  Local Anki → AnkiWeb through the sync flow
```

The backend serves the built frontend; Vite proxies `/backend` requests during
frontend development. Browser code uses backend routes for integration access.
The cache serves prepared source material locally; it does not make the optional
LLM or AnkiWeb services available offline.

Key locations: `main.py`, `backend/app.py`, `backend/services.py`,
`frontend/src/App.tsx`, `external_apis/`, and `tools/`. The active local note index
lives in `backend/note_index.py`; `main.py` remains the root browser launcher.
Integration and test module names use snake_case. Module moves preserve project-root
resolution, CLI commands, resource paths, and collection contracts.

### Retired legacy workflows

`RawNotesEditor.py`, `main.py --app -e`, and the raw/prepared-file workflow were
removed on 2026-11-19 (`L-001`), including their vocabulary directories. English-word
resolution belongs to dictionary CLI capture or the browser's current-word processing.
The manual `main.py --db` maintenance CLI, standalone Anki inspection helpers,
direct-folder audio export, and unused fixed-model/deck-moving wrappers were also
retired. Active browser index operations and cached audio upload remain. See the
[cleanup record](roadmap.md#completed-legacy-code-cleanup-2026-11-19).

## State ownership

| State | Intended authority / role | Current implementation and qualification |
| --- | --- | --- |
| Pending vocabulary/order | Source word file itself | Main/book `.txt` files are live consuming queues; `Q-001` retired the SQLite word snapshots |
| Anki notes, cards, decks, learning state | Local Anki | Access through AnkiConnect; local indexes/journals do not replace the collection |
| Dictionary source | Retained HTML/audio snapshot | Shared local files with metadata; no routine refresh, per ADR 0003 |
| Stored-field rules | Agreed note contracts | Current parser/auditor covers `en_word` syntax only |
| Save verification/recovery | Local operation journal | Expected/observed content and original decks support read-back/retry; acknowledged-but-unverified creation is recorded distinctly |
| Source consumption/recovery | Exact-entry removal receipt and file backup | `source_resolutions` records before/after fingerprints and completion; current entry IDs reject stale requests |
| Unfinished-word UI selections | Optional convenience | Current drafts persist; owner accepts redoing selections, and possible removal is `Q-002` |
| Review traversal | Current browser state | Current temporary snapshot supports revisiting study-marked items; red/orange have the same attention-marker meaning |

`Q-001` removed duplicated word-queue state, not all uses of SQLite. Source workspace
metadata stores settings and one entry-bound draft/reference; pending counts and
the next word are read from the actual file. Homepage upload/paste, queue editing,
and independent queue creation/deletion were retired. See
[ADR 0004](decisions/0004-file-backed-word-queues.md) and [queue rules](features/vocabulary-queues.md).

## Main runtime workflow

Intended/confirmed direction:

1. Take the current entry from the source word queue.
2. Use Diki source content to establish the relevant English headword and Polish alternatives.
3. The owner evaluates existing-note redundancy and selects useful translations.
4. Create a note or deliberately refresh an older note. Refresh preserves existing decks.
5. Resolve only the current source entry after the appropriate outcome; preserve concurrent capture.

Current safeguards include source-entry-scoped save intents, Anki read-back,
archive-before-exact-entry-consumption, and replay of interrupted removals. Save
verification itself no longer implicitly cleans the main file: a source workspace
consumes its own entry, while tag/flag review saves consume no file. The precise
workflow gaps remain visible in the feature/contract pages rather than being
presented as already implemented architecture.

`S-001` implements warning-and-continue for acknowledged creation followed by an
unavailable confirmation request. The journal distinguishes positive submission,
verified saves, and acknowledged-but-unverified completion. Actual mismatches,
profile changes, and updates remain strict. Accepted saves retain their original
source association; **Retry queue removal** uses it to finish only local source
consumption without calling Anki, including after a restart.

## Known mismatches and open areas

- `Q-001` is implemented: source files own queues; exact original entries are consumed
  independently of lookup spelling, with append-safe writes and stale-request checks.
- Headword-first lookup is implemented: Diki returns the original-cased identity,
  then Anki/index candidates are checked against it. Case-distinct dictionary
  meanings/resources remain separate; see [ADR 0005](decisions/0005-diki-headwords-and-case.md).
- Custom/edited Polish text remains possible; selection-only is a tentative decision.
- Prefetch discovers text lists, without the intended bounded-buffer-to-existing-note preparation tier.
- Acknowledged-create confirmation-fetch failures warn and continue (`S-001`);
  source-removal failures expose a local-only retry with precise error feedback.
- Detailed review-completion mechanics and some failure/preservation rules still need owner input.
- The standard checks, hooks, and CI enforce the offline test boundary through `tools.test_offline` (`T-002`). See [development](development.md).

See the [feature map](features.md), [contracts](index.md#rules-and-reference),
[roadmap](roadmap.md), and [to-do list](../to-do). Current walkthrough work records
these gaps; implementation happens separately.
