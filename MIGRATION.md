# Browser UI Migration Plan

## Goal

Replace the Tkinter `FlashcardApp` workflow with a polished local browser UI.
The application remains a local Python program that creates English to Polish
Anki notes using Diki, optional Gemini help, downloaded Diki audio, and
AnkiConnect.

This migration does not replace the existing terminal tools. In particular,
`tools/diki_lookup.py` keeps appending words to `words_to_add.txt`.

## Design Decisions

- Use React + TypeScript with Vite for the browser UI.
- Use FastAPI for the local Python backend.
- Bind the backend to `127.0.0.1`. Diki, Gemini, AnkiConnect, Anki media
  files, and local data are never accessed by browser JavaScript directly.
- Use `/backend/...` for backend routes, not `/api/...`. The prefix separates
  backend routes from browser pages and static assets; it is not a public API
  versioning scheme.
- Replace the JSON note index with one local SQLite database. On first run,
  import the existing `DATABASE_PATH` JSON index and retain a backup.
- Keep the local note index. It provides fast duplicate checks without having
  to query all notes from Anki for every submitted word.

## Simplified Session Model

The current application has two processes: cleaning a whole file and then
adding a whole prepared file. The browser workflow combines them per word.

After the user imports words, an add session is simply an ordered queue of
words left to process, plus the current word draft and its chosen deck/model
configuration. For each word at the front of the queue:

1. Normalize it and check the local note index.
2. Look it up on Diki.
3. If Diki has no exact result, let the user choose a suggested spelling or
   skip the word.
4. Select Diki translations and optional tags.
5. Preview the card.
6. Create a new Anki note or update an existing duplicate.
7. Remove the completed or explicitly skipped word from the queue and advance.

The queue and the current draft are persisted, so closing the browser or
stopping the server preserves the exact point of progress. There is no
separate persisted batch-cleaning result or multi-stage item state machine.
Diki data can be fetched again when a resumed current word is opened.

The browser saves queue-changing actions immediately and saves ordinary draft
changes automatically after a short debounce. Per-translation text changes are
confirmed with their checkmark control. `Exit to home` flushes a pending draft
save before returning to the landing page; it is not a separate save action.

A review session uses the same simple model, but its ordered queue contains
existing Anki note IDs or card IDs selected by a tag or flag filter. It opens
the existing-card editor directly rather than performing a Diki lookup first.

SQLite state is limited to:

- `note_index`: normalized English word and Anki note ID.
- `sessions`: ID, mode (`add` or `review`), name, source/filter, selected
  deck/model, field mapping, current draft, and timestamps.
- `session_queue`: session ID, queue position, and either an original word or
  an existing note/card reference.

The queue is always ordered. When importing `words_to_add.txt`, line 1 is
processed first, then line 2, and so on. This matters because the terminal
lookup tool appends new words at the end of that file. Empty lines are ignored.
The browser snapshots the file into a new session and does not edit the source
file.

For add sessions, card target configuration is required before the first Diki
lookup. The session-level deck, note type, and field mapping apply to every
new card until the queue is complete.

## Browser Pages

### Landing Page

The landing page has three primary actions:

1. **Continue session**: list active sessions with their remaining queue size,
   current word, selected deck, and last activity.
2. **Import words**: paste a list or select a text file, then create a session.
3. **Run words_to_add.txt**: read the known project file and create a session
   whose queue keeps its file order.
4. **Review tags and flags**: inspect current Anki metadata, select a custom
   tag or colored flag, and start an ordered existing-card review session.

### Card Workspace

The workspace replaces `preparedNotesAdder.FlashcardApp`.

- Display the current word and remaining count.
- Show Diki meanings as separate semantic groups with selectable translations.
- Let each Diki translation be edited independently. Its `Edit` control turns
  only that translation into a text field; a small checkmark control confirms
  the change. A modified translation shows its own `Reset to Diki` control,
  which restores only that value to its original Diki text.
- Show spelling suggestions when Diki has no exact match.
- Provide the existing factory tags: `IMAGE`, `ERROR`, `GEMINI_DIFF`, and
  `TO_EDIT`. Add `noAudio` automatically if audio is unavailable.
- Offer Gemini as an on-demand side panel for the current word.
- Keep the next word blocked until the user creates, updates, or skips the
  current word.
- Provide an `Exit to home` button that returns to the landing page while the
  persisted session remains available to continue later.
- Use a responsive layout: focused columns on desktop and stacked panels on
  mobile.

### Batch Target Setup

After an add queue is created or resumed without a target, show a dedicated
target screen before the card workspace:

1. Display the Anki deck hierarchy as a tree and select one destination deck.
2. Display a small histogram of note types already used by cards in that deck.
3. Select the queue note type, including any collection-wide note type when the
   deck is new or empty.
4. Confirm the English, translation, and optional audio field mapping.
5. Save the target on the session, then begin the first word.

During the queue, show the batch deck and note type as compact context rather
than allowing the target to drift between words. Immediately before creating a
new card, the user can open a one-card override form. It selects another deck
and note type with its own field mapping for that card only; it never changes
the saved batch target.

The current draft stores every translation as an original Diki value and a
current value. The preview and final card use current values, including edits.
Translation edits are treated as plain text and escaped by the backend when it
builds the card HTML; the translation editor is not a raw HTML editor. Editing,
confirming, or resetting one translation never changes another translation or
its original value.

Each sense also ends with a selectable `<br>` marker. It creates a line break
only when selected, preserving the previous factory behavior without forcing a
line break between every sense.

### Tag And Flag Review

Tags and flags are distinct Anki concepts:

- Tags are custom strings attached to notes.
- Flags are colored values attached to individual cards. A note with multiple
  cards can therefore have more than one flagged card.

The landing page review section fetches an inventory from Anki, optionally
scoped to a selected deck. It displays each unique tag and each flag color with
the number of matching notes or cards. The local note index is not the source
for this inventory because it does not contain all Anki metadata.

Selecting a tag or flag creates a snapshot review queue. The user iterates it
one existing card at a time using the same translation picker, card preview,
and field-difference view as the duplicate overwrite flow.

Expected review flows:

- `TO_EDIT`: open the current card, revise translations, fields, tags, or deck,
  then complete it. The completion UI offers removal of `TO_EDIT` and defaults
  to removing it after a successful confirmed fix.
- `ERROR`: use the same edit flow, with the option to remove `ERROR` after the
  correction is saved.
- `GEMINI_DIFF`: show the current word, existing translation, and proposed
  translations to Gemini. Gemini comments on the alternatives; it does not
  automatically alter the note. The user chooses the final translations and
  can then remove `GEMINI_DIFF`.
- A colored flag: edit the note as needed, then clear or change the specific
  queued card's flag. Do not silently alter flags on sibling cards.

Tags remain editable custom strings. The UI must show proposed tag additions
and removals before saving, rather than replacing tags without confirmation.

## Anki Deck And Note Type Configuration

Anki decks do not have one intrinsic note type. A deck may contain cards from
multiple models, and an empty deck contains no model evidence. The UI must
therefore select both a deck and a note type.

Configuration flow:

1. Fetch and select an Anki deck.
2. Fetch note types already found in that deck and show them as suggestions.
3. Also allow any Anki note type, so new or empty decks work.
4. Fetch the selected model's fields, templates, and styling.
5. Configure the card factory mapping:
   - English-word field.
   - Polish-translation HTML field.
   - Audio field, if applicable.
   - Optional additional fields and default values.
6. Store this selection in the active session.

The backend validates the deck, model, and field names immediately before each
Anki write. This replaces the current hard-coded `Basic [reverse+audio]`,
`en_word`, `pl_translation`, and `audio_en` assumptions.

## Card Preview

The backend owns final card-field construction. The frontend sends semantic
data such as selected translation groups and tags, never trusted HTML.

When selections change, the UI requests a local preview. Python returns the
canonical Polish translation HTML and the final field payload that will be
sent to Anki. React renders that exact HTML in a preview panel with the word,
audio status, tags, and submitted field values.

This avoids two divergent implementations of comma and line-break formatting.
It also avoids trying to recreate Anki's template engine in the browser. The
preview accurately shows this factory's generated HTML; full Anki template,
filter, and audio rendering remains Anki's responsibility.

## Duplicate And Overwrite Behavior

When a queue word loads, check the local note index and then query Anki using
the configured English field. Verify the returned field value before treating
it as a duplicate, and repair a missing local-index entry from the Anki note
ID. If either check finds a note, fetch the actual Anki note and show:

- Its current fields with HTML rendered where appropriate.
- Its tags and decks/cards.
- A field-by-field difference between the existing note and the proposed card.
- The proposed tag and deck changes.

The English-word field is locked during an overwrite. The user can update the
remaining mapped fields, including translation and audio, after reviewing the
difference. The UI also offers an explicit `Keep existing card` action that
removes the queue word without changing Anki.

For a note with the same model, update the existing note rather than delete and
recreate it:

- `updateNoteFields` changes the selected fields.
- Tag differences are applied explicitly with `addTags` and `removeTags`.
- `changeDeck` moves existing cards when the chosen deck differs.

Updating the same note/card IDs preserves Anki review scheduling and learned
progress. Do not support note-type changes in the first migration: changing a
note type can change templates and generated cards, so it is not safe for a
learned note. When models differ, show the incompatibility and require the
user to select the existing model before updating.

The tag/flag review editor follows these same safe update rules. Editing an
existing note in place preserves review scheduling. Clearing or changing a
flag only changes the queued card's flag and does not reset its scheduling.

## Backend Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/backend/status` | Report Anki/Diki reachability, Gemini availability, and configuration errors. |
| `GET` | `/backend/sessions` | List resumable sessions. |
| `POST` | `/backend/sessions` | Create a session from pasted words or an uploaded text file. |
| `POST` | `/backend/sessions/from-words-to-add` | Create a session from `words_to_add.txt` in file order. |
| `GET` | `/backend/sessions/{id}` | Return the session, current draft, and ordered remaining queue. |
| `PATCH` | `/backend/sessions/{id}` | Save deck/model selection and field mapping. |
| `POST` | `/backend/sessions/{id}/current/lookup` | Normalize, index-check, and look up the current word in Diki. |
| `PATCH` | `/backend/sessions/{id}/current` | Save spelling choice, translations, tags, or a skip action for the current word. |
| `POST` | `/backend/sessions/{id}/current/preview` | Build canonical HTML and return the proposed Anki field payload. |
| `GET` | `/backend/sessions/{id}/current/existing-note` | Fetch the existing duplicate note and its comparison data. |
| `POST` | `/backend/sessions/{id}/current/commit` | Create or update the Anki note, update the local index, and advance the queue. |
| `POST` | `/backend/sessions/{id}/current/skip` | Remove the current word or review card from the queue without changing Anki. |
| `POST` | `/backend/sessions/{id}/current/custom-card` | Create a manually populated note in a chosen deck/model, index the queue word, and advance the queue. |
| `PATCH` | `/backend/sessions/{id}/queue` | Replace the remaining words in an add queue; clear the current draft if its word is removed. |
| `POST` | `/backend/gemini/translate` | Return Gemini's on-demand Polish explanation. |
| `POST` | `/backend/gemini/review-translations` | Ask Gemini to compare the current and proposed translations without changing the note. |
| `GET` | `/backend/review/inventory` | Return unique custom tags and colored-flag counts, optionally for one deck. |
| `POST` | `/backend/review/sessions` | Create an ordered review session from one selected tag or flag. |
| `GET` | `/backend/decks` | List Anki decks. |
| `GET` | `/backend/deck-tree` | Return the nested Anki deck hierarchy for batch target selection. |
| `POST` | `/backend/deck-context` | Return models and card counts already detected in a selected deck. |
| `GET` | `/backend/models` | List available Anki note types. |
| `POST` | `/backend/model-schema` | Return a model's fields, templates, and styling. |

## AnkiConnect Additions

Extend the existing wrapper around its `invoke` method with support for:

- `deckNames`
- `findCards`
- `cardsInfo`
- `notesInfo`
- `modelNames`
- `modelFieldNames`
- `modelTemplates`
- `modelStyling`
- `updateNoteFields`
- `addTags` and `removeTags`
- `changeDeck`
- Documented AnkiConnect flag search (`flag:1` through `flag:7`) for inventory.
  Flag mutation is isolated behind a dedicated adapter because AnkiConnect v6
  does not document a flag-write action; the installed plugin must support the
  generic card-value setter before the UI can clear or change a card flag.

## Reliability Requirements

- Add explicit timeouts to Diki, Gemini, and AnkiConnect requests.
- Return structured backend errors instead of relying on `print` output.
- Do not advance the queue after a failed create or update.
- Offer a custom-card escape hatch for raw queue words: choose a deck and note
  type, populate every model field manually, then save and advance the queue.
- Keep the existing behavior of creating a note with `noAudio` when Diki audio
  cannot be downloaded.
- Update the local note index immediately after a successful create, including
  its in-memory duplicate-check cache.
- Treat Anki and SQLite as separate systems: mark a queue item as committing,
  call Anki, then persist the local result. On restart, reconcile an unfinished
  commit against Anki before retrying it.
- Make the local index path a documented setting again. The current README
  calls `DATABASE_PATH` obsolete even though `NotesDatabase` requires it.

## Diki Scraper Regression Tests

`external_APIs/dikiApi.py` scrapes a changing third-party HTML page with
BeautifulSoup, so it needs a growing regression corpus rather than only
print-based live tests.

Extract the HTML parsing from HTTP requests into pure parser functions. The
Diki client fetches the page, while the parser receives the page HTML and a
searched phrase. This lets tests verify parsing without live network access.

Create a fixture-based test suite with this shape:

```text
tests/
  diki_cases/
    manifest.json
    eyepatch.html
    broad-walk.html
    whatever-floats-ones-boat.html
  test_diki_regression.py
```

`manifest.json` is the editable edge-case registry. Each entry names the word,
the saved Diki HTML fixture, and the expected outcome: exact translations,
expected suggestions, or no result. Adding a discovered edge case only
requires saving its response HTML and adding one manifest entry; no new test
function is needed.

Example manifest entry:

```json
{
  "word": "whatever floats one's boat",
  "fixture": "whatever-floats-ones-boat.html",
  "expectedTranslations": [["co komu pasuje"]],
  "expectedSuggestions": []
}
```

The regression test loads every manifest entry and asserts the exact expected
parser outcome. Include cases for phrases, punctuation, nested `stopword`
spans, alternate spellings, ambiguous Diki entities, missing words, and words
whose English and Polish spelling is identical.

Keep a separate opt-in live Diki test for manually refreshing or investigating
fixtures. It must not be part of the normal test suite because Diki content,
availability, and page markup can change independently of this project.

## Terminal Tools

Keep these workflows separate from the browser UI:

- `tools/diki_lookup.py` and its append-only `words_to_add.txt` behavior.
- Database inspection, synchronization, and deletion commands.
- Raw file preprocessing and its interactive spelling prompts.

The browser's per-word Diki correction is a direct part of card creation, not
a replacement for the terminal preprocessing tool.

## Implementation Order

1. Add FastAPI, Uvicorn, Pydantic, React, TypeScript, and Vite.
2. Add SQLite persistence and one-time JSON note-index import.
3. Extract Tkinter-independent Diki, AnkiConnect, Gemini, note-index, and
   HTML-formatting services from the current modules.
4. Add Anki deck/model discovery, schema validation, duplicate loading, and
   same-note update operations.
5. Implement the backend session, lookup, preview, commit, and Gemini routes.
6. Implement Anki tag/flag inventory, lightweight review sessions, and the
   Gemini translation-comparison prompt.
7. Build the landing page, ordered add/review queue flows, and import sources.
8. Build the card workspace, preview, duplicate diff, tag/flag review, and
   overwrite confirmation UI.
9. Serve the compiled frontend from FastAPI and update the README and `.env`
   documentation.
10. Add the fixture-backed Diki scraper regression corpus and an opt-in live
    Diki refresh/integration check.
11. Replace network and side-effect-only tests with mocked unit and backend
    contract tests; retain opt-in real Anki/Diki integration checks.
