# Diki: content identity and curation contract

Last updated: 2026-11-21.

Specification status: English headword and Polish selection compatibility goals,
acceptable alternate headwords, human selection, and the missing-entry
definition/destination are confirmed. Recovering selected text is sufficient;
original sense-group identity is not required. Exact Polish encoding and the
tentative selection-only direction remain open. Historical missing-note formats
are outside the current review focus. Cache/snapshot policy, dialect-neutral audio,
and the current CLI-only role of examples are recorded. Detailed fetching/layout
rules and remaining workflow expectations are still being reviewed.

Implementation status: existing lookup and selection functionality is present;
the full compatibility goal is not established as enforced or achieved.

Verification status: source inspection and an owner-provided page excerpt, with
the missing-note structure subsequently inspected in live Anki. No live Diki
request, compatibility audit, or new parser test was performed in this discussion.

## Diki compatibility

**Diki compatibility** covers both the identity of the stored English word and
the relationship of stored Polish content to Diki's extracted translation strings:

- **English compatibility:** Anki's `en_word` uses a headword under which Diki
  represents the relevant entry, rather than merely the original lookup query or
  encountered inflection.
- **Polish compatibility:** comparing translations extracted from Diki HTML with
  stored `pl_translation` should allow code to identify which translation strings
  the owner selected, using predictable content/serialization rather than guesses
  about manually rewritten text.

The owner first named the English goal, then explicitly extended the goal to
Polish selections. Identification of selected text is sufficient; identifying the
original sense group for that text is unnecessary. Exact stored-field encoding
is still open; this is not yet a complete field parser contract.

For the normal Diki-backed vocabulary workflow, this is the intended identity of
the English content. The owner always wants Diki's stored English form.

The owner's conceptual model is a mapping:

```text
Diki English key → Polish translations
```

Diki can interpret a query as an entry under a different English headword. Mirror
that distinction in the workbench. This describes the owner's desired integration
model; Diki's private database implementation and internal keys are not exposed
or independently verified. The observable evidence is the relevant entry's
displayed English headword in dictionary content.

A successful lookup URL or a section title repeating the search term is not, by
itself, proof that the term is an entry headword.

### Resolution belongs to capture or current-word processing

The owner confirms that dictionary CLI capture resolves the relevant Diki entry
before appending the English word. That input is already Diki-compatible in the
English sense. Manual/book/historical inputs can still need resolution.

The browser's per-word lookup and spelling choices supersede the old whole-list
raw/prepared preprocessing workflow, which was removed on 2026-11-19. Vet the current
word as it is processed; no separate pre-vetted full list is required by the owner.
See [vocabulary source rules](../features/vocabulary-queues.md) and completed
retirement `L-001` in [to-do](../../to-do).

### Confirmed example: `causes` → `cause`

Source supplied by the owner:
[Diki query for causes](https://www.diki.pl/slownik-angielskiego?q=causes).

The owner pasted page content showing a query/section for `causes`, a main
headword `cause`, noun and verb meanings, and a separate related-phrases section.

| Concept | Value |
| --- | --- |
| Original queued text / lookup query | `causes` |
| Relevant Diki headword | `cause` |
| Intended stored Anki `en_word` | `cause` |

Do not preserve `causes` in `en_word` solely because it was queued. Likewise, do
not derive `cause` by an independent stemming assumption: the dictionary entry
provides the identity. The pasted content is a documented owner example, not a
captured raw-HTML regression fixture or a claim about a fresh HTTP response.

Source completion concerns the current original queue entry; other pending
variants remain unevaluated until their own turn. See
[vocabulary queue rules](../features/vocabulary-queues.md).

### Compatibility goal and existing notes

The owner aims to make normal Diki-backed English and Polish content compatible,
which is expected to be useful for future processing. Existing collection entries
may not all meet that goal, particularly manually created older notes.

This is a target, not evidence that the whole collection currently complies. No
new collection migration, rewrite, or compatibility-audit implementation was
requested or performed in this interview batch.

The existing [`en_word` version 3 contract](../../note-data-contracts.md) validates
stored syntax; it does not establish dictionary membership or Diki compatibility.
The compatibility goal does not silently change that parser, its allow-list, or
its version. Exact casing/spacing comparisons are not yet specified here.

### Multiple genuine headwords

If the relevant Diki entry has several genuine English headwords or alternative
spellings, the owner does not consider the choice between them important. Any
such headword is acceptable for compatibility with that entry.

A UI option to choose among them would be a nice addition, with low priority. Do
not make manual selection a mandatory step or treat this minor preference as a
blocker. No specific automatic ordering/preference was chosen in the discussion.
This applies to actual headwords of the relevant entry, not unrelated suggestions
or the page's related-phrases section.

## Human translation selection

The application presents Diki translation alternatives and the owner chooses a
diverse set they judge relevant to know. Selection is not restricted to the one
meaning that prompted the lookup.

There is intentionally no strict algorithm for what counts as representative.
The selection UI exists to support the owner's judgment. Do not turn frequency,
number of senses, or book context into mandatory automatic selection rules.

When the alternatives seem very different, [LLM assistance](../features/llm-assistance.md)
provides quick explanatory help. Its purpose is understanding the word/meanings;
the owner still chooses the useful translations.

This establishes selection authority, not every editor rule: final formatting and
edit behavior still need specification. Diki groups may remain useful for
presenting alternatives in the UI without becoming required stored provenance.

## Polish compatibility and refreshing existing notes

The current extraction produces a list of lists of translation strings, and the
owner selects some of those strings. The goal is that code could later extract
those strings from Diki HTML and compare them with stored Polish content to
determine exactly what was selected.

Older notes were manually authored. Their visible translation choices can be
reasonable while their stored wording/format is not predictably comparable with
the extractor's output. Refreshing an existing note during normal new-word
processing is therefore useful even when the owner selects the same translations:
it rewrites the content through the app's deterministic construction path.

This explains the purpose of the existing overwrite/update feature. It is not
merely a duplicate workaround or a feature for visibly changing meanings. See
[existing-note refresh](../features/existing-note-refresh.md).

### Observed construction and limits

- `FactoryService.translation_html` HTML-escapes selected string values, joins them
  with commas, and uses a selected break marker for some sense separators.
- The stored values come from editable draft `value` strings, not a check that
  each value remains equal to the original Diki text. The UI also permits custom
  translations. The owner's tentative direction for these features is below.
- Commas are also possible inside translation text; optional breaks do not provide
  an unconditional record of every original group boundary.
- A saved regression case for `flimsy` has the identical string `marny` in two
  different groups. The owner does not require distinguishing those source groups
  when recovering selected text, so this is not itself a compatibility blocker.

These observations explain the remaining design questions, not a decision to
replace the current field format or reject existing content. Plain extracted
strings are the comparison goal; HTML escaping/separators and any normalization
need explicit rules before a parser or compatibility audit can be implemented.

### Confirmed reconstruction scope

Recover which translation text values were selected. The original Diki sense
group/occurrence is not necessary, including the uncommon case of the same text
appearing in several groups. This does not request removing grouping from the UI
or decide display order, separators, or how repeated text is presented.

### Tentative direction: selection-only translations

The owner rarely used translation editing in the new UI and recognizes its
tension with Polish compatibility. They are leaning toward eventually removing
the ability to alter/add Polish translations in the normal workflow and allowing
only selection of original extracted strings.

**This is not a final decision.** The owner explicitly wants to think about it.
Keep the editing/custom-translation UI in place until the decision is settled;
do not implement its removal as part of this documentation. See
[the open roadmap decision](../roadmap.md#open-decision-selection-only-polish-translations).

The exact Polish serialization/parsing contract also remains open. Do not make
continued walkthrough progress depend on immediately settling these two matters.

Only `en_word` syntax currently has an agreed parser in the existing field-contract
document. This semantic goal does not by itself define a new `pl_translation`
parser, version, migration, or historical verification result.

## Interesting words missing from Diki

When a genuinely missing word/phrase is interesting enough to learn, the owner
adds it to a separate **Diki-missing deck in Anki**.

**The only defining criterion is that the word/phrase does not exist in Diki.**
Its content may be a substitution, paraphrase, translation, or another format;
format does not broaden or change the deck's definition.

That provides an intentional path for vocabulary without a suitable Diki entry;
do not force such content to pretend to be Diki-compatible. Live Anki inspection
on 2026-11-17 established the deck as `English::Diki_missing`, containing 36 notes,
all of type `Basic dikiMiss [+image]`. Its fields are `en_word`, `pl_translation`,
and `image`. See [the Anki structure snapshot](anki.md#diki-missing-deck) for the
observed structure.

The owner describes the existing deck as a mixture of past plans/ideas and content
they could not find in Diki. Do not derive a uniform missing-note field contract
from those historical examples. Further questions about its images, substitutions,
or formatting are parked so the walkthrough can cover the main project workflow.

A temporary HTTP/lookup failure does not by itself demonstrate a genuinely missing
entry. Existing field-contract documentation excludes the missing note type from
its audit scope; that scope is unchanged by this inventory.

## Pronunciation audio

The owner's requirement is a suitable pronunciation recording for the relevant
English word. **British and American recordings are equally acceptable.**

British-first arose from the original implementation: the owner manually inspected
some pages, found British recordings commonly available, and used American audio
as a fallback. It was not a deliberate dialect preference or a hard product rule.

The current `external_apis/diki_audio.py` selector can retain its ordering: exact
spelling, then space-only variants, with British before American within each tier.
That is observed fallback behavior, not an acceptance criterion requiring British
speech. No chooser, dialect setting, or change to selection order was requested.
Audio remains an enrichment to the core English/Polish note content.

## Example sentences

Current owner-confirmed purpose: **show examples of usage during CLI lookup** so
the owner can understand how a word is used. The parser extracts examples attached
to Diki meanings and `tools/diki_lookup.py` displays English with Polish when
available.

The owner also has plans to add example sentences to Anki notes, but explicitly
defers this as a substantial feature for another session. Existing parsing and the
Anki `sentences` field do not establish a current note-population requirement.
No sentence migration, selection UI, generation source, or stored-field contract
is being specified by this answer. See
[the deferred sentence feature](../roadmap.md#future-discussion-example-sentences-in-anki-notes).

## Cached source material and compatibility checks

The owner wants Diki HTML to be retained and reused for two purposes: offline
processing of pending vocabulary, and repeated compatibility/contract/refinement
work on words already in Anki. A repeated check should not require downloading
the same HTML again merely because it is a new run.

Raw HTML is reusable source input, separate from extracted strings and stored
Anki values. The owner accepts an accumulated **rolling snapshot**, downloaded
across weeks, as the comparison reference. Diki compatibility refers to that saved
source; routine expiry or refreshing already available content is not required.

The owner will manually evaluate assertion/test failures when wording or HTML
changes may be responsible. Do not silently refresh source or alter expected
results/notes to force compatibility. See
[ADR 0003](../decisions/0003-rolling-diki-snapshot.md).

See [cache and background preparation](../features/offline-cache.md) for the two
confirmed goals, observed mechanics, and existing-note coverage gap.

## Implementation evidence and gaps

- [`external_apis/diki_api.py`](../../external_apis/diki_api.py), `lookup`, returns
  translation groups or suggestions, without a separate resolved-headword field.
- `parse_meanings` accepts entities whose header contains the normalized requested
  phrase. It does not independently resolve every inflection to a different
  headword. A query such as the owner's `causes` example can require selecting and
  looking up the appropriate suggestion under current behavior.
- [`backend/services.py`](../../backend/services.py), `lookup_current`, checks Anki
  using the submitted word before fetching Diki, and stores `sourceWord` and `word`
  in the draft. This is not yet an explicit dictionary-headword-first identity
  contract throughout the pipeline.
- Q-001 now identifies and consumes the original current source occurrence,
  independently of the selected lookup/saved spelling. Saving `cause` can therefore
  consume original `causes` without removing another queued `cause`. This fixes
  source bookkeeping, not the broader headword-first lookup/matching gap above.
- A generic custom-card path exists, but no reviewed rule guarantees routing
  genuinely missing words to the owner's specific missing deck and note type.
- Deterministic serialization of current draft values exists, but does not alone
  prove that saved translations match Diki strings or are recoverable as selected
  values. Original source-group identity is not required. The compatibility goal
  and its remaining decisions are above.

## Authority

These intended rules come from the owner's fourth through nineteenth interview batches
on 2026-11-17. Batch 6 fixes the missing-entry definition and parks historical
exception details. Batch 8 extends compatibility to Polish selections and explains
existing-note refresh. Batch 9 removes the need for source-group identity and
records selection-only editing as tentative. Batch 12 establishes cache reuse for
both pending and existing vocabulary. Batch 13 accepts rolling-snapshot retention
and manual evaluation of source-change failures. Batch 14 clarifies dialect-neutral
pronunciation and CLI examples, with note sentences deferred. Batch 19 confirms
CLI-compatible English capture and deprecates whole-list preparation. Missing-note
observations come from read-only live Anki queries.
See the [walkthrough checkpoint](../review.md) for answers and unresolved questions.
