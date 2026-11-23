# Project purpose and scope

Last updated: 2026-11-22.

Status: foundation confirmed by the owner during the handbook walkthrough.
Detailed feature and integration rules remain under discussion. See the
[walkthrough checkpoint](review.md) for progress and unanswered questions.

## Purpose

Anki Flashcards Factory is a personal workbench for turning English vocabulary
worth learning into curated English–Polish flashcards in the owner's existing
Anki collection.

The core result is a **1:N English-to-Polish content relationship**: one English
word or phrase with multiple Polish translations selected as representative by
the owner. The default note type is `Basic [reverse+audio]`, whose current
templates test English → Polish and Polish → English. The 1:N relationship
describes translation content rather than the number of generated Anki cards.

Audio, images, and similar enrichments are useful additions to that core result.
They are not what originally made the workflow useful.
For pronunciation, either British or American audio is acceptable; British-first
is an implementation fallback, not a learning preference.

The `IMAGE` tag marks words the owner has assessed as possible image-card
candidates. Evaluation started partway through the collection's history; untagged
notes are not necessarily unsuitable. Creating image notes during processing and
migrating old notes form a larger feature deferred for a later discussion. See
[future work](roadmap.md) and the [Anki workflow](contracts/anki.md).

## Content identity and selection

**Diki compatibility** covers both English identity and Polish selections:

- `en_word` uses the relevant Diki English headword, rather than the original
  lookup form. For example, queued `causes` should produce `cause` in Anki.
- Stored Polish translations should be predictably comparable with the strings
  extracted from Diki HTML, so code can identify which alternatives were chosen.
  Original Diki sense-group identity is not required for that comparison.

Normal Diki-backed vocabulary is intended to meet this goal; the existing
collection may not yet be fully compatible. Refreshing manually authored older
notes during word processing serves this goal even when visible translations
remain the same. See [existing-note refresh](features/existing-note-refresh.md).

Refresh is a gradual cleanup aid for historical translation artifacts. The owner
also has a broader collection-cleanup idea, but needs structured target data
contracts before deciding how to migrate existing content. This is an important
reason for defining the handbook/contracts now. Future cleanup might reduce the
need for per-word refresh; no retirement decision has been made.

The owner selects a diverse set of Polish translations they personally consider
useful to know. There is intentionally no strict algorithm for representative
selection. The owner is considering a selection-only UI to preserve original
strings, but removing editing/custom additions is not yet a final decision. An
interesting word/phrase genuinely missing from Diki goes to a separate Diki-missing
deck in Anki.

See the [Diki contract](contracts/diki.md) for terminology, rationale, evidence,
and distinctions from the existing syntax-only field contract.

## Assistance with ambiguous meanings

LLM assistance was added as a quick way to understand English words whose Polish
translation alternatives appear very different. A definition, translation, or
explanation helps the owner interpret those alternatives without researching each
uncertainty manually on the web. Gemini is the current optional integration.

The owner remains responsible for selecting what to learn. Newer ideas involving
word definitions are deferred for a later feature discussion. See
[LLM assistance](features/llm-assistance.md).

While studying in Anki on a phone or laptop, the owner also flags older cards that
need later attention. Red and orange have the same practical meaning. Revisiting
those cards supports manual editing, deleting, or reconsideration; see
[marked-note review](features/marked-note-review.md).

CLI dictionary lookup also displays usage examples. Adding example sentences to
finished Anki notes is a separate future feature, deferred for another session.

## Offline work and reusable dictionary data

The Diki cache has two primary goals:

1. Prepare HTML/audio so pending vocabulary can be processed into Anki notes
   offline, without fetching dictionary resources during the session.
2. Accumulate reusable source HTML for vocabulary already in Anki, supporting
   repeated compatibility checks, contract work, tests, and future refinement
   without downloading the same pages on every run.

Existing-note source data is part of the intended scope, not merely an incidental
performance benefit. An explicit one-time inventory and remote preparation now
support filling only missing HTML; complete existing-collection coverage is not
established merely by implementing that mechanism. See
[cache and background preparation](features/offline-cache.md).

The owner confirmed first-100-entry windows for every pending vocabulary file on
2026-11-23, refining the original rough main/book buffer target. Those HTML/audio
jobs precede existing-note HTML coverage; one startup drain immediately imports
and ACKs results in background. Successfully downloaded content is retained as a
rolling snapshot collected over weeks. Routine refreshing is unnecessary; source
changes exposed by checks will be evaluated manually by the owner. See
[ADR 0003](decisions/0003-rolling-diki-snapshot.md).

## Audience and scope boundary

The primary user is the project owner. Publishing the code on GitHub does not
make a general-purpose service the current product goal.

The workbench is deliberately tied to the owner's existing Anki decks, note
types, and collection structure. There is currently no plan to untangle it into
a standalone production service. This is the present scope, not a permanent
prohibition on future changes.

See [ADR 0001: Personal workbench scope](decisions/0001-personal-workbench-scope.md)
for this decision and its consequences.

The supported operating setup is confirmed: backend and CLI on the owner's Mac,
Anki on that same Mac, and the browser UI used locally. The owner expects to keep
using this arrangement. The local backend/AnkiConnect defaults and macOS launchd
scheduler fit that target. See [architecture](architecture.md) for the component
map and the distinction between intended state ownership and current mismatches.

## Two main vocabulary sources

Source paths below are relative to the separate directory selected by
`ANKI_FACTORY_DATA_DIR`. Code and durable personal data were split on 2026-11-22;
the data repository versions queues, cached HTML/MP3, SQLite, and deliberate backups.
See [data placement](features/data-storage.md) and [ADR 0006](decisions/0006-separate-data-root.md).

### Everyday discoveries

The owner encounters English words at work, university, and in daily life, then
decides which are worth learning.

Chosen words go into the main vocabulary file,
`words_to_add/words_to_add.txt`. The owner previously appended them manually and
now has a CLI tool for capture. The file is a mutable pending queue: it grows
through capture, including concurrently with processing, and shrinks as words
are resolved.

CLI capture resolves the Diki English entry before appending, so those captured
words are Diki-compatible input. Older manual/book input can still need the main
app's per-word spelling/entry resolution. The former separate whole-list
raw/prepared preprocessing path was retired on 2026-11-19; see
[the retirement record](features/maintenance-and-tooling.md#whole-list-preprocessing-retired-l-001).

The file itself is the authoritative queue. `Q-001` implemented direct file-backed
processing and removed the duplicated SQLite pending-word snapshot. The homepage
opens actual main/book sources; pasted/uploaded queue creation and queue editing
were retired at the owner's request. **Discard from queue** removes the current
pending entry without changing Anki, including when an existing note already
covers the word. See
[ADR 0004](decisions/0004-file-backed-word-queues.md). Restoring unfinished-word
drafts is optional convenience: the owner is comfortable reselecting
translations and may remove that feature later (`Q-002`). It is not a core
durability requirement.

### Kindle reading

The owner highlights words while reading Kindle ebooks. Periodically, a file
containing words from one book is imported into this project; Fablehaven is an
existing example of this book-based source.

Book files are also mutable pending queues and shrink as words are individually
resolved. Historically, the owner downloaded a Kindle file manually and placed
it in the repository. The implemented source picker discovers `.txt` files under
`words_to_add/`, including the existing Fablehaven file and subdirectories.
Current input is one word or phrase per line, sometimes with import artifacts,
such as surrounding quotes in `"flimsy"`. This infrequent workflow may change;
JSON containing words/phrases was mentioned as a possibility, not a committed
implementation requirement.

Exact artifact cleanup remains open; original-file/current-entry association is
implemented by Q-001. No Kindle integration or automatic highlight extraction is
implemented or requested.
See [vocabulary queue rules](features/vocabulary-queues.md) for lifecycle details,
concurrency requirements, and current implementation gaps.

Resolution is per entry: processing one word must not trigger cleanup of other
pending words or variants. Diki's representation and the owner's evaluation inform
whether the current item is already covered in Anki; raw spelling alone is not a
basis for automatic queue-wide deduplication. See
[ADR 0002](decisions/0002-per-entry-vocabulary-resolution.md).

## Workflow and motivation

Originally, the owner:

1. Encountered and selected vocabulary worth learning.
2. Looked it up on Diki's website.
3. Manually copied Polish translations judged representative.
4. Cleaned unwanted HTML from the copied content.
5. Created an Anki flashcard.

The project automated the translation acquisition/cleanup work and later added
MP3 downloading and other conveniences.

The owner considers the original HTML-cleanup problem solved by the implemented
core functionality. It should be recorded as completed motivation and capability,
not repeatedly presented as an outstanding feature. Later work has added useful
extras around the established vocabulary workflow.

## Confirmed priorities

- Support vocabulary the owner has deliberately chosen to learn.
- Support the two main input sources: everyday discoveries and book highlights.
- Produce the curated English-to-multiple-Polish-translations result.
- Aim for Diki-compatible English headwords and recoverable Polish selections.
- Support refreshing older notes through the same selection/construction workflow.
- Keep translation selection under the owner's judgment.
- Support offline processing of prepared vocabulary.
- Reuse cached dictionary source material for existing-note checks and refinement.
- Preserve the benefit of avoiding manual copying and HTML cleanup.
- Treat audio and images as enrichments to the vocabulary content.
- Fit the owner's Anki structure; generalizing to a standalone production service
  is outside the current goal.

Detailed formatting, editor behavior, and acceptance criteria for enrichments
remain to be discussed. Translation selection itself is intentionally subjective.

## Evidence and authority

The purpose, source descriptions, priorities, and scope above come from the
owner's foundation, vocabulary-lifecycle, Diki, and Anki-workflow answers on
2026-11-17. These statements explain intent; they are not a claim that every
related path has been runtime-verified.

Relevant implementation and history include:

- [`tools/diki_lookup.py`](../tools/diki_lookup.py): dictionary CLI and optional
  append to the main word list.
- [`backend/services.py`](../backend/services.py): browser lookup, translation
  construction, and Anki workflows.
- [`note-data-contracts.md`](../note-data-contracts.md): already agreed field rules
  and their limited audit scope.
- The [history baseline](review.md#repository-evidence-baseline), including browser,
  cache, audit, and verified-save milestones.
