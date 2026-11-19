# Architecture and operating constraints

Last updated: 2026-11-19.

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
| Pending vocabulary/order | Source word file itself | Main/book files are consuming queues; current SQLite add-queue copies conflict with this direction (`Q-001`) |
| Anki notes, cards, decks, learning state | Local Anki | Access through AnkiConnect; local indexes/journals do not replace the collection |
| Dictionary source | Retained HTML/audio snapshot | Shared local files with metadata; no routine refresh, per ADR 0003 |
| Stored-field rules | Agreed note contracts | Current parser/auditor covers `en_word` syntax only |
| Save verification/recovery | Local operation journal | Expected/observed content and original card/deck assignments support read-back/retry |
| Unfinished-word UI selections | Optional convenience | Current drafts persist; owner accepts redoing selections, and possible removal is `Q-002` |
| Review traversal | Current browser state | Current temporary snapshot supports revisiting study-marked items; red/orange have the same attention-marker meaning |

`Q-001` removes duplicated word-queue state, not all uses of SQLite. See
[ADR 0004](decisions/0004-file-backed-word-queues.md) and [queue rules](features/vocabulary-queues.md).

## Main runtime workflow

Intended/confirmed direction:

1. Take the current entry from the source word queue.
2. Use Diki source content to establish the relevant English headword and Polish alternatives.
3. The owner evaluates existing-note redundancy and selects useful translations.
4. Create a note or deliberately refresh an older note. Refresh preserves existing decks.
5. Resolve only the current source entry after the appropriate outcome; preserve concurrent capture.

Current source-inspected safeguards include durable save intents, Anki read-back,
archive-before-source-cleanup, and replay of interrupted operations. The precise
workflow gaps remain visible in the feature/contract pages rather than being
presented as already implemented architecture.

For the discussed case of acknowledged note creation followed by a failed
confirmation request, intended behavior is notification and continuation. Current
blocking read-back behavior is slated for simplification as `S-001`; the existing
journal is an implementation fact, not an owner requirement for handling every
rare failure with a blocking recovery flow.

## Known mismatches and open areas

- SQLite add queues are independent snapshots; the desired queue is the source file (`Q-001`).
- Current source cleanup targets matching saved words in the main file, rather than a general original-entry association for all source files.
- Initial duplicate lookup precedes Diki resolution, while intended identity follows the dictionary headword.
- Custom/edited Polish text remains possible; selection-only is a tentative decision.
- Prefetch discovers text lists, without the intended bounded-buffer-to-existing-note preparation tier.
- Failed follow-up confirmation currently blocks acknowledged-create completion; intended behavior is warning-and-continue (`S-001`).
- Detailed review-completion mechanics and some failure/preservation rules still need owner input.
- The standard checks, hooks, and CI enforce the offline test boundary through `tools.test_offline` (`T-002`). See [development](development.md).

See the [feature map](features.md), [contracts](index.md#rules-and-reference),
[roadmap](roadmap.md), and [to-do list](../to-do). Current walkthrough work records
these gaps; implementation happens separately.
