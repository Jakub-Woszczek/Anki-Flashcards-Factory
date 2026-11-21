# Project handbook walkthrough — checkpoint

Last updated: 2026-11-21.

## Post-walkthrough Q-001 implementation — 2026-11-21

The owner separately approved and implemented the file-backed queue refactor:

- Main/book files now directly own pending vocabulary/order; SQLite persists
  settings, an entry-bound draft/reference, save history, and removal receipts.
- Browser upload/paste, queue naming/creation/editing/diffs/deletion were retired.
- Discard replaces generic skip and keep-existing; it only removes the current
  source entry and never deletes an Anki note. Duplicate-note deletion was removed;
  existing notes are refreshed in place.
- Completion consumes the exact original occurrence even after lookup spelling
  changes. Concurrent CLI appends are preserved; entry IDs reject stale requests
  and durable receipts protect interrupted-removal retries. Review saves no longer
  implicitly clean the main vocabulary file.
- Read-only comparison found 25 entries in the old main SQLite queue absent from
  its file. The owner requested appending them at the end in queue order. This was
  completed, checked again, then the database was backed up and snapshot rows retired
  while retaining target settings. There were no imported add queues to export.

Current authority: [queue rules](features/vocabulary-queues.md) and
[ADR 0004](decisions/0004-file-backed-word-queues.md). `Q-002` draft removal remains
optional; `S-001` confirmation simplification remains pending. The interview batches
below are historical evidence, not a description of today's queue implementation.

Verification: `python -m tools.check` passed on 2026-11-21 (Ruff, Pyright,
132 offline tests with 2 live checks skipped, frontend TypeScript/build).
No live Anki/Diki requests or collection changes were made during Q-001 work.

## Post-walkthrough implementation update — 2026-11-19

The separately authorized deprecated-workflow cleanup is complete:
`RawNotesEditor.py`, `raw_notes/`, and `prepared_notes/` (including their contents)
were removed, along with their entry points and tests (`L-001`/`T-001`). The expanded
approval also retired manual index-maintenance commands and scan helpers,
`AnkiUtils`, direct-folder audio export and its tests, unused Anki creation/deck-moving
wrappers, and dead helpers/attributes. Active browser index operations remain.
See the [cleanup record](roadmap.md#completed-legacy-code-cleanup-2026-11-19).

Full unittest discovery ran 107 tests with no failures and 2 opt-in live Diki tests
skipped under a temporary socket-connection guard. The subsequent repository cleanup
completed `T-002` with the committed `tools.test_offline` runner, shared quality
command, hooks, CI, and guard regressions. Python modules were normalized and IDE
artifacts untracked; application behavior remains unchanged. See
[development tooling](development.md). No live collection or Diki requests were
used for verification. The interview batches below remain historical evidence.

## Resume here

We are documenting this existing project through a guided conversation with its
owner. The owner wants durable explanations of goals, constraints, features,
completed work, external-source rules, intended behavior, and decision rationale.
They should not have to explain this documentation effort again in a new session.

**Walkthrough status:** baseline complete. The owner will choose the next work
priority in a new session; no priority decision is required to close this review.
Start future sessions at [the handbook index](index.md), read the relevant rules,
then review root [to-do](../to-do) and [roadmap](roadmap.md). Let the owner choose
the next task before implementation; do not restart this interview.
The owner prefers warning-and-continue for acknowledged note creation followed
by failed follow-up confirmation, rather than blocking on read-back. Recorded as
`S-001` for separate implementation; the current code is still stricter.
The test boundary is confirmed: routine tests are offline with fixtures/fake Anki;
real Anki/Diki checks are explicit integration actions. Current discovery passes
offline after legacy-test retirement; `T-002` now enforces the standard runner. See
[development and verification](development.md).
The three initial live smoke tests and two retired scan-helper tests were removed
in the separately authorized cleanup (`T-001`). Whole-list raw/prepared preprocessing
was also removed (`L-001`); the browser resolves words during processing, and
dictionary CLI capture appends already compatible English entries.
Flags are now understood: the owner primarily sets them during
Anki study for later attention; red/orange have the same practical meaning.
See [marked-note review](features/marked-note-review.md).
Operating scope is confirmed: backend/CLI, Anki, and local browser UI on the
owner's Mac, now and going forward. The handbook now has an
[index](index.md), [feature map](features.md), and [architecture overview](architecture.md).
Unfinished-word draft recovery is optional convenience; reselecting translations
is acceptable. Possible removal is recorded as optional `Q-002`, not a firm
requirement. Do not keep drilling into low-value persistence conveniences.
**Documentation-only instruction:** from batch 15 onward, record behavior-change
requests in the root [to-do](../to-do) for separate implementation. Wording such as
"change this" during this walkthrough is not permission to alter application code.
The word source file itself is the authoritative queue; `Q-001` implemented removal
of the duplicated SQLite queue on 2026-11-21. See
[ADR 0004](decisions/0004-file-backed-word-queues.md). Do not ask more questions
about synchronizing mirrored queues; that topic is settled.
Pronunciation is dialect-neutral; either British or American is acceptable.
Sentence extraction currently supports CLI usage examples; adding sentences to
notes is explicitly deferred as a whole feature. See the
[Diki contract](contracts/diki.md#pronunciation-audio) and [roadmap](roadmap.md).
Cache preparation should protect a bounded offline buffer (roughly 100 main-queue
words first, then a similar book buffer), then prepare existing-note HTML.
The owner accepts a retained rolling Diki snapshot accumulated over weeks and
will manually evaluate source-change discrepancies. These policies are settled
in principle; exact buffer mechanics are not a blocker. See
[cache rules](features/offline-cache.md) and
[ADR 0003](decisions/0003-rolling-diki-snapshot.md).
The cache has two owner-confirmed primary purposes: process pending words offline,
and accumulate reusable Diki source data for existing Anki words so repeated
contract/compatibility checks and future refinement do not re-download it each
time. Current prefetch scans text lists, not Anki vocabulary directly. See
[cache and background preparation](features/offline-cache.md).
LLM assistance is documented as quick help understanding words and diverse Polish
translations; newer definition-related ideas are explicitly deferred. See
[LLM assistance](features/llm-assistance.md).
Deck preservation
on refresh is confirmed and the requested prospective correction is implemented:
updated cards keep their existing decks; historical moves are left as-is.
65 isolated tests passed for the change. Code/tests only were committed as
`60cdb9f`; the owner subsequently requested a separate commit for the handbook,
README, and todo changes. The owner clarified that refresh is a
gradual cleanup aid; broader old-note cleanup requires target contracts first.
See [existing-note refresh](features/existing-note-refresh.md) and
[future cleanup](roadmap.md#future-discussion-contract-first-cleanup-of-older-notes).
Polish compatibility needs selected text values, not original Diki sense-group
identity. A selection-only UI is a tentative direction; the owner needs time to
think, so leave editing/custom additions intact and revisit later. See
[the open decision](roadmap.md#open-decision-selection-only-polish-translations).
Refreshing old notes has a confirmed objective: rebuild Polish content so selected
Diki strings can be identified by comparison, even if visible meanings do not
change. `TO_EDIT` and `ERROR` are legacy/deprecated workarounds; `GEMINI_DIFF` means
closer manual examination after a translation discrepancy. See
[existing-note refresh](features/existing-note-refresh.md) and the
[Diki contract](contracts/diki.md#polish-compatibility-and-refreshing-existing-notes).
Deck names are historical batch labels with soft conventions. The default type
is `Basic [reverse+audio]`; `IMAGE` is a partial-coverage candidate marker.
Image-note creation/migration is a substantial separate feature, deferred in
[roadmap.md](roadmap.md). Do not start that feature interview yet.
The Diki-missing definition is settled: the word/phrase does not exist in Diki.
The owner explicitly parked that deck's mixed historical image/substitution
details as a detour. Do not resume those questions. Live structure is recorded in
the [Anki contract](contracts/anki.md). Multiple genuine Diki headwords are acceptable;
a manual chooser is a low-priority convenience, not a blocker.
The owner has defined **Diki compatibility**, confirmed headword storage and human
translation selection, and described the missing-entry destination. See the
[Diki contract](contracts/diki.md). Vocabulary lifecycle and per-entry scope are captured in
[vocabulary queue rules](features/vocabulary-queues.md) and
[ADR 0002](decisions/0002-per-entry-vocabulary-resolution.md). Do not reopen exact
book-file location as a prerequisite; the owner has given sufficient context.
The first foundation answers are captured in
[project purpose and scope](project.md) and
[ADR 0001](decisions/0001-personal-workbench-scope.md).
Purpose, main sources, core output, personal-workbench scope, and the operating
environment are confirmed. Remaining quality/workflow rules are tracked below.

To resume:

1. Read this checkpoint and any handbook files it links to.
2. Read the latest user answers, if present; update this checkpoint before moving on.
3. Check current repository status and inspect the files/history and live Anki
   facts relevant to the next topic. Query observable structure before asking the
   owner to describe it. The baseline below is historical evidence, not a fresh
   verification.
4. Continue with the unanswered questions. Do not restart the whole interview.
5. After each answered batch, write the resulting rules and rationale into the
   appropriate handbook files and update coverage, gaps, and next questions here.

## Confirmed documentation decisions

The owner explicitly chose:

- **A lightweight Markdown handbook**, version-controlled in this repository.
- Selected [arc42](https://arc42.org/overview) concepts: goals, constraints,
  external interfaces, architecture, and quality requirements.
- [Architecture Decision Records](https://adr.github.io/) for significant choices,
  their rationale, trade-offs, and superseding decisions.
- [Diátaxis](https://diataxis.fr/) distinctions between instructions, reference,
  and explanation. Organize content by reader need without forcing a large template.
- An incremental interview that produces documentation as understanding develops.
- Dependency-aware questions: establish independent foundations first, then use
  earlier answers to avoid irrelevant or redundant questions.

OpenSpec and Spec Kit were researched as alternatives. Neither is being adopted
as part of this walkthrough.

## Agreed working method

For each area:

1. The assistant describes findings from code, documentation, and relevant commits.
2. The assistant asks a small batch of questions, normally 1–3.
3. The owner explains intended behavior and why. Informal answers and examples work.
4. The assistant turns those answers into concise rules and rationale, identifying
   ambiguity instead of inventing requirements.
5. Record the result, then move on; return to unresolved questions when necessary.

Keep these categories distinct:

| Category | Meaning |
| --- | --- |
| Current behavior | What the implementation does, with evidence |
| Intended behavior | What the owner says it should do |
| Rationale | Why a rule or decision exists |
| Gaps | Bugs, missing functionality, conflicts, or unresolved decisions |
| Evidence | Relevant files, tests, commits, and verification results |

Existing code, test expectations, commit messages, and old plans are evidence, not
automatic approval of product requirements. Preserve already explicitly agreed
contracts and raise conflicts. Mark proposed rules as proposed until confirmed.
Separate implementation status from specification status and verification status.
Record historical verification as historical; inspecting a test is not running it.

For each batch, summarize what was understood, persist it, and ask the next useful
questions. Ask for clarification when an answer is ambiguous; avoid an additional
approval round for every unambiguous restatement.

**Inspect first, then ask about intent.** The owner explicitly corrected the
assistant for asking about Anki structure that can be queried from the running
application. Use read-only queries to inspect relevant decks, model fields,
templates, representative notes, and exceptional content before interviewing.
Do not ask the owner to transcribe accessible facts. Ask about rationale, desired
behavior, or ambiguity left after inspection. Use relevant samples and aggregates
instead of dumping the collection. Record observed state separately from policy.

**Maintain breadth and relevance.** This is a project handbook/intent walkthrough,
not a collection-cleanup audit. Establish the main workflows and important design
choices before drilling into historical edge cases. The owner corrected a detour
into Diki-missing image/substitution notes: record that deck's simple definition,
park its incidental inconsistencies, and move on. Discovering a discrepancy does
not automatically make it a question, requirement, or prioritized fix.

**Record changes; do not implement them during this walkthrough.** In batch 15 the
owner explicitly directed that statements requesting changes should become items
in the root `to-do` list, with implementation in a separate session. This supersedes
the earlier practice of implementing a scoped correction during the interview.
Continue editing handbook/checkpoint/todo files only. The deck-preservation fix
and its code-only commit `60cdb9f` predate this instruction and remain historical
completed work; they do not create ongoing permission for more code changes.

**Use precise questions.** The owner rejected a broad "what should survive closing
and reopening?" question as vague. Give one concrete scenario and ask about a
specific outcome, rather than bundling queue state, settings, drafts, and review
progress into one question.

## Documentation destinations

Create or expand files as the relevant topics are discussed. This table describes
the intended structure, not files that already all exist.

| Destination | Responsibility |
| --- | --- |
| `docs/index.md` | Handbook navigation and document authority |
| `docs/project.md` | Purpose, users, goals, scope, constraints, quality goals, glossary |
| `docs/features.md` | Capability inventory, specification and implementation status |
| `docs/architecture.md` | System context, interfaces, components, state ownership, important flows |
| `docs/contracts/diki.md` | Observed source structure and agreed interpretation/fetching rules |
| `docs/contracts/anki.md` | Anki concepts, integration, targeting, media, and save/update rules |
| `note-data-contracts.md` | Existing authority for agreed stored-field content contracts |
| `docs/features/*.md` | Detailed behavior and acceptance scenarios where useful |
| `docs/decisions/*.md` | Significant decisions with status, context, rationale, and consequences |
| `docs/history.md` | Completed software milestones and separately identified data operations |
| `docs/roadmap.md` | Prioritized future work and unresolved decisions |
| `docs/review.md` | This effort's purpose, coverage, current checkpoint, and next questions |
| `AGENTS.md` | Short coding-agent entry point and handbook maintenance instructions |

Keep README focused on installation and everyday use. Link rather than duplicate
authoritative rules. Preserve useful historical plans and research with clear
status labels when reconciling them. Record substantial decisions in ADRs; ordinary
field rules or feature details do not each need their own ADR.

## Dependency-aware coverage map

All areas below were initially inspected at varying depth. Owner-confirmed
coverage is tracked separately from inspection. Inspect relevant implementation
more deeply before interviewing each area.

This is a dependency map, not a rigid script. Reorder or skip questions based on
what the owner has already explained. Revisit broader repository coverage at the
end so that small tools and legacy paths are not forgotten.

| Area | Establish first | Next status |
| --- | --- | --- |
| Purpose, audience, real workflow, definition of a good result | No prerequisites | Foundation captured in `project.md`; detailed quality rules and platforms deferred |
| Vocabulary sources, list ownership, queue meaning | Purpose and real workflow | Q-001 implemented source-file queues and exact-entry bookkeeping; optional drafts retained, possible removal Q-002 |
| Diki authority, meaning structure, matching, examples | Purpose and content needs | English/Polish text compatibility captured; source-group identity unnecessary; exact encoding pending |
| Anki concepts, existing note types, fields, templates | Audience and definition of a good result | Batch-label rationale, default type, and partial IMAGE candidate semantics captured; image feature deferred |
| Translation selection, editing, provenance, preview | Diki interpretation and Anki content expectations | Subjective text selection captured; selection-only UI tentative/deferred; grouping provenance unnecessary |
| Creation, duplicates, updates, verification, cleanup, recovery | Queue ownership, Anki identity, editing rules | Refresh/deck rules captured; acknowledged-create confirmation failure should warn/continue (S-001); other details limited to documented intent |
| Review and repair of existing notes | Anki tags/flags and update rules | Study-origin flags and common red/orange attention meaning captured; completion mechanics not yet specified |
| Audio selection, media handling | Diki source rules and Anki field needs | Either dialect accepted; British-first is historical fallback; broader media failure/storage rules pending |
| Offline cache, background prefetch, scheduling | Source ownership, audio needs, operating constraints | Two goals, bounded queue buffers, and rolling snapshot retention captured; population mechanics deferred |
| Gemini and other external services | Content authority and human editing workflow | LLM explanatory purpose captured; definition-related ideas deferred; detailed prompting/invocation not a blocker |
| Browser/CLI boundaries, legacy tools, architecture, deployment, testing | Establish operating constraints early; inspect details after workflow decisions | Same-Mac scope, legacy deprecation, and offline test boundary confirmed; enforcement T-002 deferred |

For each area, track open questions and resulting document links here as the
interview progresses. A purpose answer may already resolve audience or deployment
questions; do not ask them again mechanically.

## Repository evidence baseline

Initial inspection covered README, existing plans/contracts, application paths,
tests, and Git history. The latest 35 commit summaries, recent milestone file
statistics, and selected diffs for saves, Diki fetching, and note contracts were
reviewed. That initial phase did not execute live queries. Later, in batch 5,
read-only AnkiConnect queries inspected the running collection. See the
[Anki snapshot](contracts/anki.md). In batch 10 the owner requested a prospective
deck-preservation fix. Five new regressions reproduced the bug before the fix;
65 isolated tests passed afterward. No live collection writes or full field/Diki
compatibility audits have been performed in this effort.

Initial committed baseline inspected: `6eb461a`. The deck-preservation correction
was subsequently committed as `60cdb9f`, code/tests only, at the owner's request.
Its Git commit date is 2026-11-18; the dates below follow commit metadata.

| Date | Commit(s) | Recorded development step |
| --- | --- | --- |
| 2026-11-06 | `a279243`, `5d7992b` | Diki parser regression fixtures; AnkiConnect editing/media support |
| 2026-11-06 | `5ebe0ef`, `6437e8c` | SQLite index/queues; local browser workspace replacing Tkinter |
| 2026-11-06 | `8296a73` | Browser workflow and migration documentation |
| 2026-11-06 | `8a66247`, `219e14a` | Bilingual examples in parsing and styled CLI output |
| 2026-11-09 | `ad2345a` | Shared offline Diki cache and scheduled prefetching |
| 2026-11-11 | `d8560c8` | Audio discovery, cache improvements, interactive/background separation |
| 2026-11-14 | `a5f478f` | Incremental note contracts and read-only audit |
| 2026-11-16 | `7e724bc` | Save read-back verification, recovery, archival, source-list cleanup |
| 2026-11-16 | `6eb461a` | Data operation: removed 483 occurrences of 444 verified words, per commit record |
| 2026-11-18 | `60cdb9f` | Preserve existing card decks during refresh and verify original assignments on read-back/recovery; code/tests only |

The data-operation counts above come from the historical commit record and were
not reverified against Anki.

Uncommitted work observed before creating this checkpoint: changes to
`frontend/src/App.tsx`, `words_to_add/words_to_add.txt`, and `.DS_Store`, plus
untracked `frontend/src/TranslationEditor.tsx` and `cloudflare/`. These are not
committed milestones. Recheck their state before drawing conclusions.

### Existing documents and conflicts to reconcile

- [README](../README.md): current operational guide and save/cache behavior.
- [Note data contracts](../note-data-contracts.md): explicitly agreed `en_word`
  version 3, audit scope, migration checkpoint. Other fields remain undefined.
- [Browser migration plan](../MIGRATION.md): design and rationale, partly superseded.
- [Offline plan](../plan.md) and [research](../research.md): implementation and
  investigation history; not a current general roadmap.
- [to-do](../to-do): unstructured backlog, including queue editing that now has
  implementation and tests.

Known discussion points, not newly agreed requirements:

- The old browser plan says source lists are never edited; the newer save flow
  deliberately removes matching words after verification.
- The browser plan describes persisted review sessions; current review uses an
  unsaved browser snapshot.
- The `en_word` contract is used for audits, not enforced by the normal write path.
- Diki headwords now define normal stored identity, with a separate Diki-missing
  destination. Reset provenance and duplicate identity across profiles still need
  clarification. Both source types are consuming
  queues, and processing one entry must not resolve other pending entries.
  Implementation of source/occurrence tracking remains open.

## Answers captured: foundation, batch 1

Owner's explanation, summarized on 2026-11-17:

- Everyday English words encountered at work, university, and in life are selected
  as worth learning and added to the main `words_to_add.txt` file. Capture was
  previously manual; a CLI tool is now used.
- The second main source is Kindle reading: highlighted words are periodically
  imported as a file for one book, such as Fablehaven.
- Originally the owner manually copied representative Polish translations from
  Diki, cleaned HTML, and created Anki flashcards. The project automated this and
  later added MP3 downloads and other extras.
- The core output is a 1:N English-to-Polish translation relationship. Audio and
  images are useful additions. Do not infer card-template direction/count from 1:N.
- The manual copying/HTML-cleanup problem is already solved, not an active gap.
- This is mainly a personal workbench coupled to the owner's Anki deck/note-type
  structure. Public GitHub hosting does not imply a standalone product goal, and
  there is no current plan to generalize it into a standalone production service.

Recorded in [project.md](project.md) and
[ADR 0001](decisions/0001-personal-workbench-scope.md).

Deferred, not forgotten: detailed formatting/editing rules and specific operating
environments belong with their areas. Batch 4 establishes translation selection as
intentionally subjective; do not seek an algorithm the owner does not want. Do not
repeat audience or basic source questions that are already answered.

## Answers captured: vocabulary lifecycle, batch 2

Owner's explanation, summarized on 2026-11-17:

- Both main and book files are queues to consume; both should shrink when entries
  are resolved. Book files are not intended as untouched highlight archives.
- The main list also grows concurrently through CLI capture. This is expected.
- A word successfully added to Anki does not need to return to the pending list.
- A word already in Anki should not be kept for later addition.
- The owner can decide an old pending word is no longer worth learning; that means
  deleting it from the word list without creating an Anki entry.
- Current Kindle files are approximately one word/phrase per line but may include
  punctuation artifacts. No exact stripping rule has been agreed.
- Book import is infrequent and may change format, possibly to JSON containing
  words/phrases. This possibility is not an immediate feature commitment.
- The owner welcomes follow-up questions when an answer leaves ambiguity.

Recorded in [vocabulary queue rules](features/vocabulary-queues.md) and reflected
in [project.md](project.md). No application behavior was changed by this capture.

## Answers captured: source follow-ups, batch 3

Owner's explanation, summarized on 2026-11-17:

- Processing a word must not trigger evaluation/removal of other queued entries.
  Each entry is evaluated when taken for processing.
- Diki HTML clarifies how the dictionary stores the English word. In the owner's
  example, queued `causes` may correspond to Diki's `cause`. This informs checking
  Anki and evaluating redundancy; it is not a new verified dictionary fixture.
- Similar forms cannot safely be treated as equivalent without the owner's
  evaluation. Automatic queue-wide variant deduplication is not a current goal.
- Kindle files were historically downloaded manually and placed somewhere in the
  repository. The owner found the prior location/import question vague. Do not
  demand an exact folder or settled import mechanism now.
- The owner recalls artifact-stripping code designed not to strip meaningful
  characters. Its location/current applicability has not been established.
- The example `"flimsy"` → `flimsy` accurately represents book-file artifacts.

Recorded in [vocabulary queue rules](features/vocabulary-queues.md),
[project.md](project.md), and
[ADR 0002](decisions/0002-per-entry-vocabulary-resolution.md).

## Answers captured: Diki identity and selection, batch 4

Owner's explanation, summarized on 2026-11-17:

- Always store the English form under which Diki represents the relevant entry.
- The owner supplied a query URL for `causes` and pasted page content with main
  headword `cause`. The desired Anki `en_word` is `cause`.
- Preserve the term **Diki compatibility**: `en_word` should correspond to a Diki
  entry headword, conceptually a key mapping to Polish translations. This is the
  owner's integration model, not verified access to Diki's private database schema.
- Existing English fields may not all be compatible; achieving compatibility is
  a goal expected to be useful in future. No bulk rewrite was requested.
- Translation selection is a diverse set the owner judges relevant to know, with
  no strict rules. This is why the selection UI is important.
- Interesting words/phrases missing from Diki are added to a Diki-missing deck in
  Anki. The exact deck name, note type, fields, and authoring flow remain open.

Recorded in [Diki contract](contracts/diki.md), reflected in
[project.md](project.md) and [vocabulary queue rules](features/vocabulary-queues.md).
The supplied excerpt is not a raw-HTML fixture or a newly performed live lookup.

## Answers captured: headword preference and inspect-first correction, batch 5

- The owner has encountered multiple Diki headwords before and does not regard
  choosing among genuine alternatives as important. A chooser could be nice, but
  is a low-priority convenience.
- The owner pointed out that Anki is running and instructed the assistant to query
  it before asking factual questions about its structure. This is now part of the
  walkthrough method, not just a one-time action.

The assistant then queried live Anki through the project's configured connection:

- `English::Diki_missing`: 36 notes / 36 cards, all `Basic dikiMiss [+image]`.
- Fields: `en_word`, `pl_translation`, `image`. One English-to-answer template;
  `image` is not referenced.
- 8 notes tagged `substitute` contain English equivalents in `pl_translation`.
- 14 notes contain images. Two have no translation text, so the template currently
  has no separate answer content for those notes.
- Normal model fields/templates were also inspected: `Basic [reverse+audio]`
  has two templates and 1,886 notes; `Basic [reverse+audio+image]` has one template
  and 376 notes. These are snapshot counts, not fixed requirements or a full audit.

Recorded in [Diki contract](contracts/diki.md) and
[Anki contract](contracts/anki.md). Only read operations were performed.

## Answers captured: missing definition and scope correction, batch 6

- Diki-missing has one defining criterion: the word/phrase does not exist in Diki.
  It may contain substitution notes or any other content format. Do not redefine
  it as a general home for all nonstandard vocabulary.
- The existing deck mixes content from past plans/ideas with words the owner
  could not find in Diki. Its historical consistency is not the current concern.
- The owner explicitly said further questions about that deck's images/details
  were veering off the main course of the walkthrough. Those questions are parked,
  not unresolved prerequisites or requests for cleanup.

Updated [Diki contract](contracts/diki.md) and [Anki contract](contracts/anki.md).
The inspect-first instruction still applies, but findings must be filtered for
relevance to this documentation effort rather than pursued indiscriminately.

## Answers captured: deck history and image candidates, batch 7

- Deck numbering originally tracked batches of added vocabulary.
- Names sometimes described note content (images, substitutions, or a more specific
  description), but that was a soft convention. Determining actual contents would
  require inspecting each deck; do not infer strict routing/model rules from names.
- The owner reports newer decks from approximately the D-labelled period are
  larger and contain well-made notes primarily added through this app. This is
  historical context, not a collection-wide quality audit.
- `Basic [reverse+audio]` is the default note type.
- The image tag marks a word the owner considered a possible image-card candidate.
  The actual code/live spelling is `IMAGE`. Evaluation started partway through
  collection history, so absence of the tag does not mean unsuitable/evaluated.
- Image-note migration and creation during processing are another large feature
  with prior ideas, explicitly deferred to their own future discussion.

Recorded in [Anki contract](contracts/anki.md), [project.md](project.md), and the
new [roadmap](roadmap.md). The owner endorsed questions about main deck/type
purpose as relevant to this walkthrough.

## Answers captured: Polish compatibility and tag lifecycle, batch 8

- The compatibility goal also applies to Polish translations: given Diki's
  extracted list-of-lists strings and stored Polish content, code should be able
  to identify exactly which strings the owner selected.
- Newer notes are created through extraction/selection; older notes were authored
  manually. Updating an existing note during new-word processing is intended to
  make its stored Polish content deterministically Diki-compatible, even if the
  same visible translations are selected again.
- `TO_EDIT` is deprecated, originating when broken processing and inability to
  skip forced the owner to mark a note for later correction. That situation is no
  longer expected in normal processing.
- `ERROR` has the same historical workaround role for bad HTML/processing when
  skipping was unavailable.
- `GEMINI_DIFF` marked a word/translation mismatch with Gemini's translation for
  closer manual examination after addition. It is not an automatic correction.

Recorded in [Diki contract](contracts/diki.md), [Anki contract](contracts/anki.md),
[project.md](project.md), and [existing-note refresh](features/existing-note-refresh.md).
The goal is captured; exact field encoding and enforcement are not yet agreed.

## Answers captured: text identity and tentative editing direction, batch 9

- The owner rarely used translation editing in the new UI and sees the conflict
  with compatibility. They are leaning toward eventually removing the ability to
  alter/add Polish translations and selecting only original extracted strings.
- The owner explicitly needs to think about it. This is tentative, not approval
  to remove editing/custom additions. Keep the UI intact and revisit later.
- Recovering the original meaning group is unnecessary. Even if the same word
  appears in multiple groups, selected text identity is enough.
- This does not request removing groups from the selection UI or deciding a new
  serialization format. Exact stored Polish encoding remains open for later work.

Recorded in [Diki contract](contracts/diki.md),
[existing-note refresh](features/existing-note-refresh.md), [project.md](project.md),
and [roadmap](roadmap.md). Move on rather than pressing for a final editing policy.

## Answers captured: deck preservation and gradual-cleanup role, batch 10

- Moving refreshed notes into the queue's selected deck was a mistake. Existing
  notes should stay in their current decks during future processing.
- Historical moves may be left as they are. No restoration is requested.
- Refresh was introduced to gradually fix old manually created notes with Polish
  translation artifacts using clean, deterministic Diki extraction/construction.
- The owner has ideas for a future broader cleanup, possibly involving hundreds
  or thousands of manually authored notes. Structured target contracts are needed
  before choosing how to migrate their content.
- A completed broader cleanup might eventually make this refresh aid less useful
  or unnecessary. This is future rationale, not a decision to remove it now.
- The answer elaborated purpose, not an exhaustive preservation policy for every
  tag, field, or scheduling property. Do not manufacture confirmation of those.

Implemented the explicitly requested prospective deck fix in `backend/services.py`
and `backend/word_completion.py`. Updates snapshot validated original card/deck
assignments, do not call deck movement, and verify the same assignments on read-back
and recovery. Creation still verifies its chosen target deck.

Verification command, passed 65 tests:

```bash
python -m unittest tests.test_word_completion tests.test_target_selection tests.test_review_stateless tests.test_diki_resources tests.test_audio_sync tests.test_sync_rate_limit
```

Regressions cover the original deck, sibling cards in different decks, persisted
recovery after a deck mismatch, unavailable card metadata, and the review update
path. Tests use in-memory Anki fakes and temporary storage. No live notes were moved.

Recorded in [existing-note refresh](features/existing-note-refresh.md),
[Anki contract](contracts/anki.md), [project.md](project.md), and [roadmap](roadmap.md).

## Answers captured: LLM rationale and code-only commit, batch 11

- The owner requested committing the completed deck fix, code only. Commit
  `60cdb9f` contains `backend/services.py`, `backend/word_completion.py`,
  `tests/test_word_completion.py`, and `tests/test_diki_resources.py`. No handbook,
  README, frontend, vocabulary-list, or other working changes were committed.
- LLM assistance responded to difficulty interpreting English words with widely
  varying Polish translations. A quick definition, possible translation, or
  explanation helps the owner understand the word and interpret alternatives.
- The motivation was convenient help instead of manually researching uncertainty
  on the web. Gemini is the current implementation; the owner speaks of the LLM
  role more generally without requesting a provider expansion.
- The owner has newer ideas involving word definitions, explicitly deferred for
  a later feature discussion. Do not design structured-definition fields or
  redesign prompts as an assumed requirement now.
- Precise independent-versus-contextual prompt behavior and automatic invocation
  were not settled by this answer. Purpose is sufficiently clear to move on.

Recorded in [LLM assistance](features/llm-assistance.md), [project.md](project.md),
[Diki contract](contracts/diki.md), and [roadmap](roadmap.md).

## Answers captured: two cache goals, batch 12

- Initially the app fetched HTML/MP3 during processing, tying word addition to
  internet access. The first cache goal was adding prepared queued words offline.
- The second goal emerged from field-contract and old-note refinement plans:
  English/Polish compatibility checks need the corresponding Diki HTML.
- Re-downloading HTML on every test/check is wasteful. Accumulate and reuse source
  data over time, including for vocabulary already in Anki, not just pending lists.
- This source dataset supports repeated checking, later refinements, and changes.
  It does not establish that full compatibility auditing or existing-note cache
  population is already implemented.

Recorded in [cache and background preparation](features/offline-cache.md),
[project.md](project.md), [Diki contract](contracts/diki.md), and
[roadmap](roadmap.md). No new downloads or application-code changes were made.

## Answers captured: preparation buffers and snapshot retention, batch 13

- The owner usually adds roughly 20–50 words per week or less frequently, rather
  than hundreds within a few days. This is context, not a usage limit.
- Prepare the front of the main queue first, with roughly 100 words as a safe
  starting buffer, and a similar buffer for book vocabulary. Once covered,
  download HTML for older/existing notes rather than exhausting all pending lists.
- 100 is illustrative. Exact configuration and which book lists are covered are
  implementation details not yet settled; do not repeatedly ask for them now.
- Refreshing already downloaded content is unnecessary work. The owner accepts
  a retained snapshot accumulated over multiple weeks, rather than a single-day
  or continually fresh dictionary copy.
- Diki can change wording or HTML. The owner will manually investigate assertion
  or test failures to distinguish source changes from code defects and accepts
  that this may occur. Do not auto-refresh/rewrite expectations to hide failures.

Recorded in [cache rules](features/offline-cache.md), [Diki contract](contracts/diki.md),
[project.md](project.md), [roadmap](roadmap.md), and
[ADR 0003](decisions/0003-rolling-diki-snapshot.md). No runtime behavior was changed.

## Answers captured: pronunciation and CLI examples, batch 14

- British-first was a historical implementation choice based on a few manually
  inspected pages where British recordings were commonly available. American
  audio was used as fallback, not because the owner prefers British pronunciation.
- The owner wants a suitable recording and does not care whether it is British
  or American. No selection-order change is requested.
- Sentence fetching currently exists to show word-usage examples in the CLI.
- There are plans for example sentences on Anki notes, but the owner explicitly
  defers this as a substantial feature for another session. Do not design or
  implement that feature during the current walkthrough.

Recorded in [Diki contract](contracts/diki.md), [Anki contract](contracts/anki.md),
[project.md](project.md), and [roadmap](roadmap.md). No application code changed.

## Answers captured: authoritative file queue and documentation-only rule, batch 15

- The owner explicitly directed that future behavior-change requests in this
  walkthrough be added to `to-do` and implemented separately, not acted on here.
- The word file itself is the queue. The duplicated SQLite queue is unnecessary
  state that introduces synchronization problems and does not match the intended
  model. Remove/refine that logic in a later implementation session.
- This settles the queue-authority topic; do not keep asking about mirror/snapshot
  synchronization. Detailed UI refresh mechanics can wait for the refactor.
- The owner rejected the general resume question as broad/vague and asked for a
  more precise one. Draft recovery was unanswered at that point; batch 16 below
  records the subsequent clarification.

Recorded task `Q-001` in root [to-do](../to-do), with details in
[ADR 0004](decisions/0004-file-backed-word-queues.md),
[vocabulary queue rules](features/vocabulary-queues.md), [project.md](project.md),
and [roadmap](roadmap.md). No application code or data was changed.

## Answers captured: optional per-word draft recovery, batch 16

- Processing a single word is little work; the owner rarely closes/leaves the UI
  before finishing it. Re-selecting unsaved translations later is acceptable.
- Draft autosave/resume was accepted as a convenience during AI-assisted UI work,
  rather than meeting a strong workflow need. Its absence would make little
  difference to the owner.
- The owner may remove it in a later session, but does not consider that necessary
  or urgent. Record a simplification candidate rather than a firm removal rule.
- This concerns per-word UI state, not the Diki source cache, source queue data,
  or durable Anki-save recovery. Do not collapse those distinct purposes.

Added optional `Q-002` to root [to-do](../to-do), and updated
[queue rules](features/vocabulary-queues.md), [roadmap](roadmap.md),
[project.md](project.md), and [ADR 0004](decisions/0004-file-backed-word-queues.md).
No application code or state was changed.

## Answers captured: same-Mac local operating scope, batch 17

- The owner confirmed backend/CLI on their Mac, Anki on the same Mac, and local
  browser UI use as both the present and continuing intended setup.
- This closes the environment-scope question; do not reopen hypothetical hosting
  or cross-platform requirements during this review.

Recorded in [project.md](project.md) and the new [architecture](architecture.md).
Added [handbook navigation](index.md) and [feature/specification map](features.md)
to make the accumulated documentation usable beyond the interview log.

## Answers captured: flags as study-time attention markers, batch 18

- Flags were not primarily used during note creation. They are easy to set while
  studying Anki on a phone or laptop when an older card now seems to need work.
- The later action may be editing, deleting, or another evaluation. Flagging
  records the need for attention, not a specific prescribed fix.
- There is little practical distinction between red and orange; both mean that
  something should be done with the item later. Do not invent per-color severity
  or stages.
- Study on the phone does not expand the Factory deployment target established
  in batch 17; keep those contexts distinct.

Recorded in [marked-note review](features/marked-note-review.md),
[Anki contract](contracts/anki.md), [feature map](features.md), [project.md](project.md),
and [architecture](architecture.md). No flags or other application state changed.

## Answers captured: deprecated preprocessing and CLI compatibility, batch 19

- Old manual word capture could produce English inputs that were not Diki
  headwords. A separate whole-list preprocessing stage prepared compatible words
  before app processing.
- The owner confirms its logic/directories are deprecated. The browser covers
  spelling/entry selection per word, which is a better place to vet it than a
  separate full-list preparation stage.
- CLI capture already resolves the English entry before appending, so captured
  English words are Diki-compatible. Do not infer that every old/manual/book line
  or Polish field has therefore been verified.

Recorded in [feature map](features.md), [queue rules](features/vocabulary-queues.md),
[Diki contract](contracts/diki.md), [project.md](project.md), and
[architecture](architecture.md). Added retirement-review task `L-001` to root
[to-do](../to-do), with context in [roadmap](roadmap.md). No legacy code/data was removed.

## Answers captured: obsolete initial live tests, batch 20

- After inspecting their provenance, the owner confirmed the three discussed
  methods were early attempts to test the initial app and may be deleted.
- Scope: `TestAnkiConnect.test_add_flashcard`,
  `TestAnkiConnect.test_move_note_to_deck`, and
  `TestRawNotesEditor.test_diki_possible_spellings`.
- Recorded deletion as `T-001` in root [to-do](../to-do), with details in
  [roadmap](roadmap.md). No methods were removed during the walkthrough, consistent
  with the batch-15 rule to implement requested changes separately.
- This does not decide the fate of the two read-only Anki tests or establish a
  blanket policy for all live integration checks.

## Test inspection and provenance evidence

Inspected source behavior:

- The README gives a selected module command for fixture/mock-backed verification;
  65 isolated tests were run for the committed deck-preservation fix.
- `tests/test_ankiConnect.py` contains unguarded live creation of an Anki note and
  movement of a fixed existing note to another deck. Its tests instantiate the
  configured real AnkiConnect client.
- `tests/test_rawNotesEditor.py` has an unguarded real Diki HTTP request.
- Other live Diki tests in `tests/test_dikiApi.py` are explicitly opt-in through
  `RUN_LIVE_DIKI_TESTS=1`, while prompt/resource tests can be isolated.
- Therefore the selected isolated suite and unrestricted discovery are currently
  different. The owner subsequently confirmed the offline/isolated boundary in
  batch 21; enforcing it is `T-002`.

Evidence: README test command and the named test modules, inspected as source
only for this question. No live tests were executed during this inspection.

Follow-up provenance lookup requested by the owner:

- Live note creation and fixed-note deck movement originate in `d301a5d`
  (2025-09-23, `Initial commit`), originally in root `test_ankiConnect.py`.
- The live raw-editor Diki request also originates in `d301a5d`, originally named
  `test_dicky_possible_spellings` in root `test_rawNotesEditor.py`.
- `2f4c6b7` (2025-12-27) reformatted the Anki calls and renamed the Diki test/method
  spelling; it did not introduce the live behavior.
- `76aa313` (2025-12-28) added dotenv setup and two read-only Anki inspection tests.
- `15f9db4` (2026-04-02) moved both files under `tests/`; the raw-editor file was an
  unchanged rename and the Anki file's import path was adjusted.
- Verified using rename-following history, blame, and original commit file contents.
  The owner subsequently approved retirement of these three methods (`T-001`);
  the broader policy was subsequently confirmed in batch 21 below.

## Answers captured: default offline test boundary, batch 21

- The owner agreed that routine automated tests should use saved Diki HTML and
  fake Anki responses offline, without touching their actual Anki collection.
- Real Anki/Diki checks are explicitly invoked integration checks. Separate
  collection audits can read real notes and cached HTML intentionally.
- This records a rule; the remaining live-test separation is not implemented
  during the walkthrough. Added `T-002` to root [to-do](../to-do).

Recorded in new [development.md](development.md), [roadmap](roadmap.md),
[architecture](architecture.md), and handbook navigation. No tests/code were changed
or executed for this policy capture.

## Answers captured: proportionate handling of failed confirmation, batch 22

- The owner considers acknowledged creation followed by failed confirmation a
  very rare case for personal use.
- Preferred behavior: show a notification that the note was created but
  confirmation failed, then continue normal word processing.
- Successful follow-up read-back is not intended to block advancement in this
  case. Record the simplification rather than preserve the current conservative
  behavior as an assumed requirement.
- The answer does not request removing all operation storage or decide every
  unknown-write/failure case. Do not expand the edge-case discussion further.

Added `S-001` to root [to-do](../to-do), with rules in
[Anki contract](contracts/anki.md), [queue rules](features/vocabulary-queues.md),
[feature map](features.md), [architecture](architecture.md), and [roadmap](roadmap.md).
No application code was changed.

## Walkthrough conclusion and next-session handoff

Baseline topics are covered at the intended project-handbook level. The owner
explicitly deferred choosing the next work item to a new session. Exact future
field contracts, deferred major features, and low-level refactor design remain
future work, not prerequisites for concluding this walkthrough.

Next-session reading order:

1. `docs/index.md` and `docs/project.md` for the handbook and goals.
2. Root `to-do` and `docs/roadmap.md` for accepted tasks versus deferred ideas.
3. Relevant contract, feature, and ADR pages before working on a chosen task.
4. This checkpoint for clarification/history when needed.

Summarize the available work briefly and let the owner choose the next task.
Do not assume every idea is an accepted change: selection-only editing and draft
removal have tentative/optional status. Check Git status before work; unrelated
user changes were present when this walkthrough ended. The owner requested a
separate documentation commit for the handbook, README, and todo changes.
The deck-preservation code/test correction was committed as `60cdb9f`.

The documentation-only constraint governed this walkthrough. Implementation
belongs to a separately requested task/session with its own explicit scope.
