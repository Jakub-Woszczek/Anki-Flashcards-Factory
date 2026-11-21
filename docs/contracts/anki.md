# Anki integration and existing collection structure

Last updated: 2026-11-21.

Status: live inventory with owner-confirmed deck history, default note type, image
candidate semantics, and missing-entry definition. Other behavior is still being clarified.
Existing stored content and templates are observations, not automatically accepted
requirements. The owner has confirmed the personal-workbench scope and a separate
Diki-missing destination; see [project scope](../project.md) and
[Diki content rules](diki.md).

## Evidence and scope of inspection

Read-only AnkiConnect queries were made against the running application on
2026-11-17 using the project's configured connection. AnkiConnect reported API
version 6.

Queried deck/model names, field names, templates/styling, note IDs/content, and card
IDs. All 36 notes in the missing deck were inspected for field-presence and tag
statistics; selected content was examined in detail. Two notes from each of the
two normal models below were also sampled. Counts are a historical snapshot.

This was a structure/content inspection, not a full field-contract or Diki
compatibility audit. No Anki data, templates, tags, decks, or sync state were changed.

## Deck context

The collection has an `English` hierarchy containing numbered groups (`1#`–`9#`,
`A1`–`A9`, `B1`–`B9`), image-labelled groups (`C2[Obrazkowe]`–`C8[Obrazkowe]`),
`C9`, `D1`, `books-IT1`, `Diki_missing`, `test`, and `toSort`. It also has a
`Domyślna` deck.

### Owner-confirmed organization and rationale

The owner historically added vocabulary in batches and numbered the batches.
Some deck names also described their note content (for example, image notes or
substitutions), while others had more precise descriptions. This was a **soft
convention**, not a consistently enforced taxonomy.

The owner reports that newer decks, approximately from the D-labelled period,
became larger because this application was the primary way of adding notes to
them, and describes those notes as well made. This is the owner's account of
their workflow/history, not a measured size ranking or an audit of every note.

Deck labels are therefore historical context, not reliable field/model/routing
rules. Determining actual contents would require inspecting individual decks;
a full classification is not needed for the current overview. No new automatic
batch-numbering or deck-routing rule was established by this answer.

A deck and a note type remain distinct. Do not infer a universal one-to-one
relationship or a strict content guarantee from the name.

## Relevant note types and actual templates

| Note type | Fields, in stored order | Current template behavior | Collection note count |
| --- | --- | --- | ---: |
| `Basic [reverse+audio]` | `en_word`, `audio_en`, `pl_translation`, `sentences` | Two templates: English/audio with sentence hint → Polish; Polish → English/audio with sentence hint | 1,886 |
| `Basic [reverse+audio+image]` | `en_word`, `pl_translation`, `audio_en`, `image` | One template: image + Polish → English + audio | 376 |
| `Basic dikiMiss [+image]` | `en_word`, `pl_translation`, `image` | One template: English → translation field; image not referenced | 36 |

Template behavior comes from the live model definitions, not the model names.
In particular, the image model currently has one direction despite `reverse`
appearing in its name. The normal-model counts are observed collection totals;
this inspection did not audit every normal note's values or generated cards.

The inspected models use Georgia, 20px, centered text, black on white, and wrapping
CSS. Treat styling as observed appearance until its intended role is reviewed.

An additional read-only query on 2026-11-17 found two notes of
`Basic [reverse+audio]` with nonempty `sentences`. The template's sentence hint is
therefore an existing capability with sparse stored content, not evidence of an
agreed sentence-population workflow or field contract. The owner subsequently
confirmed that current sentence fetching serves CLI usage examples. Adding
examples to notes is a substantial future feature, explicitly deferred to another
session. No cleanup of the existing values or automatic population is requested.

The existing [stored-field contracts](../../note-data-contracts.md) apply only to
the two normal types above and currently define only `en_word`. They exclude
`Basic dikiMiss [+image]` and `TEMP Image recall`.

## Default note workflow and image candidates

**`Basic [reverse+audio]` is the owner's default note type** for the main vocabulary
creation workflow. Its two current template directions are recorded above.

During word processing, the owner can mark a word as a candidate for a future
image-based note. The application spells this tag **`IMAGE`**
(`frontend/src/App.tsx`, `FACTORY_TAGS`); the owner's explanation referred to it
as the image tag.

The marker means the owner considered the word potentially suitable for an image
card. It does not mean the note is already of the image model, that an image has
been created, or that conversion is approved under a specified migration policy.
Candidate marking began after the collection already existed, so only some words
have been evaluated. An absent `IMAGE` tag does **not** mean a word was judged
unsuitable for an image.

Read-only tag inspection on 2026-11-17 found 83 `IMAGE`-tagged notes; the two
sampled notes (`marlin`, `weeding`) still use `Basic [reverse+audio]`. This is a
snapshot consistent with candidate marking, not a count of all suitable words.

The owner has ideas for migrating old notes and creating image-type notes during
the main word-processing flow. They explicitly identify this as another large
feature for a later discussion. The existing model/template and candidate tag do
not establish that this end-to-end feature is complete. See the
[future-work discussion list](../roadmap.md).

## Existing-note refresh and follow-up tags

Normal word processing can display an existing note, compare fields, update it
in place, or suspend it. **Discard from queue** removes the pending entry without
changing the existing note. The redundant keep-existing action and duplicate-note
deletion were retired in Q-001 at the owner's request; overwrite uses in-place
update rather than deleting/recreating learned cards. Updates
retain the note ID, lock the English field, and block changing its note type in
that path. These are current capabilities, not yet a complete owner-confirmed
duplicate/update policy.

### Owner-confirmed refresh objective

Refreshing a manually authored older note during new-word processing should make
its Polish content deterministically comparable with selected Diki strings. Even
reselecting the same visible translations can be worthwhile because the app
rebuilds their stored representation. Diki compatibility applies to Polish
selections as well as English headwords. See
[existing-note refresh](../features/existing-note-refresh.md) and the
[Diki contract](diki.md#polish-compatibility-and-refreshing-existing-notes).

This is a gradual cleanup aid for old manually created notes with artifacts. A
broader cleanup is a possible future feature, dependent on defining the target
data contracts first; its eventual completion might reduce the need for this
per-word refresh. Neither bulk cleanup nor removal of refresh is decided now.

### Deck preservation on refresh

Owner-confirmed rule: **keep an updated note's cards in their existing decks**.
The earlier behavior of moving them to the selected batch deck was a mistake.
The owner explicitly accepts historical moves as they are and requested changing
future processing only.

The backend now records each existing card's validated ID/deck mapping before the
field update, performs no deck move, and verifies that same mapping on read-back
and retry. This also preserves sibling cards deliberately placed in different
decks. New-note creation still uses and verifies the selected destination deck.
The shared update path applies this rule in both add-word and review workflows.

This change does not establish a complete policy for every other mutable field,
tag, or scheduling property. The update remains in place against the existing
note ID; no live scheduling audit was performed for this correction.

## Source queue completion

Create/update/custom saves first use the existing Anki verification rules, then
consume only their original current source entry. The saved English spelling can
differ from that original entry. Other occurrences and other source files remain
pending until evaluated. Save intents include source-entry identity so separate
occurrences do not accidentally replay one another's operations.

Discard consumes the current source entry without any Anki mutation; this also
covers deciding that an existing note is already adequate. Exiting before resolving
a word leaves it pending. Tag/flag review has no vocabulary-source association and
its saves do not implicitly clean the main list. See [queue rules](../features/vocabulary-queues.md).

## Acknowledged creation with failed follow-up confirmation

Precondition: Anki has accepted creation of the note; a subsequent confirmation/
read-back request fails. The owner considers this a very rare case in personal
use and prefers simple feedback over a blocking recovery workflow.

Intended behavior:

- Show a notification such as **"Note created, but confirmation failed."**
- Continue normal processing to the next word. Acknowledged creation is sufficient
  to complete the current source entry in this discussed case.
- Do not make successful follow-up read-back a mandatory queue-advancement gate
  for that acknowledged creation.

The current code is stricter: it retains the pending word when verification
fails. Changing that behavior is recorded as `S-001` in [to-do](../../to-do), not
implemented during this walkthrough. This decision covers the discussed successful
creation followed by a failed confirmation request; other save-error cases were
not newly specified by the answer.

The rationale is proportionate complexity for the owner's personal workflow.
This is not a request to remove all save journals, tests, or ordinary diagnostics.

## Owner-confirmed tag lifecycle

| Tag | Meaning and current role |
| --- | --- |
| `TO_EDIT` | Deprecated workaround from older faulty processing when the owner could not skip a word and marked the resulting note for later repair. Not an expected normal new-note outcome now. |
| `ERROR` | The same kind of legacy workaround for wrong HTML/processing when skipping was unavailable. |
| `GEMINI_DIFF` | Marks a word whose word/translation pairing disagreed with Gemini's translation and should be examined more closely, manually, even after addition. |

`GEMINI_DIFF` indicates a discrepancy for human examination, not proof Gemini is
correct and not authorization for automatic replacement. `TO_EDIT` and `ERROR`
may remain in existing notes or UI, but the old
[browser plan](../../MIGRATION.md#tag-and-flag-review) is not authority to treat
them as current primary workflows. No tag removal or UI change is requested by
documenting their legacy status. How manual review concludes and clears a marker
can be defined when the review workflow is discussed.

Read-only Anki inspection on 2026-11-17 found 46 `GEMINI_DIFF` notes and 14
`TO_EDIT` notes. `getTags` returned spelling `Error`, while the `ERROR` tag query
returned zero notes. These are historical observations, not prescribed workloads
or a reason to investigate tag casing now.

## Flags and attention during study

The owner mainly sets flags while studying in Anki on a phone or laptop, rather
than while creating notes. A card that was acceptable in the past may now need
editing, deleting, or another decision; flagging is a quick way to draw attention
to it for later.

**Red and orange have no meaningful distinction in this workflow.** Both mean
something needs attention. They do not define different severities, repair types,
or processing stages. Flagged items require human evaluation, not an automatic
diagnosis from their color.

Anki's flag is card-level; note-field edits can affect sibling cards, while a flag
belongs to an individual card. Phone-based Anki study does not change the
Factory's confirmed same-Mac local operating setup.

The existing review inventory found 10 red-flagged cards (flag 1), 111 orange
cards (flag 2), and 46 `GEMINI_DIFF` notes in `English` and subdecks. These are
snapshot counts. Exact completion/flag-clearing behavior remains unspecified.
See [marked-note review](../features/marked-note-review.md) for the purpose and
current implementation evidence.

## Diki-missing deck

### Definition and walkthrough boundary

Owner-confirmed definition: the word/phrase does not exist in Diki. That is the
only defining criterion; the content can include substitutions or other formats.
This is not a general bucket defined by being nonstandard.

The existing deck is a mixture of past ideas/plans and vocabulary the owner could
not find in Diki. The owner explicitly asked to stop investigating its historical
image/substitution details during this walkthrough. Preserve the observations
below as background, not active review questions, a new backlog, or instructions
to standardize this deck. Resume the main Diki-backed Anki workflow instead.

### Observed structure

- Exact deck name: **`English::Diki_missing`**.
- 36 notes and 36 cards, all using **`Basic dikiMiss [+image]`**.
- All 36 collection notes of this model are in this deck at this snapshot.
- All notes have nonempty `en_word`; 34 have nonempty `pl_translation`.
- 14 contain image markup in `image`. No inspected missing-deck note contains
  image markup in `en_word` or `pl_translation`.
- 8 notes have tag `substitute`; 1 has `noAudio`.
- There is no dedicated audio field on this model.

Current `Karta 1` front:

```html
{{en_word}}
```

Current back:

```html
{{FrontSide}}

<hr id=answer>

{{pl_translation}}
```

The `image` field is not referenced on either side. The field's presence and the
`[+image]` model label therefore do not imply that stored pictures are displayed.

### Historical content observations — parked

| Note ID | English content | Translation-field content / relevant detail |
| --- | --- | --- |
| `1662744505255` | `from behind the bars` | `zza krat` |
| `1677447779360` | `miss deadlines` | `nie dotrzymywać terminów` |
| `1678049834738` | `my bad` | `My mistake (inaczej)`, tagged `substitute` |
| `1755116817503` | `I feel you` | `<i>Zamiennik</i><br>I understand you` with stored newlines, tagged `substitute` |
| `1680299033077` | `a pile of money` | Empty translation, populated image, tagged `noAudio` |
| `1686136594724` | `kennel, doghouse` | Empty translation, populated image |

All 8 `substitute` notes store English paraphrases/equivalents in the field named
`pl_translation`. Both notes with empty translations have populated image fields,
which are currently unused by the template.

These observations do not establish that the words are absent from Diki today,
where the content originally came from, or whether these cases are intentional
formats versus historical workarounds. No dictionary lookups were made here.

Observed images and paraphrases do not change the owner-confirmed eligibility
rule. Their desired formatting has not been specified and is intentionally not
being pursued now. Existing normal-note contracts must not be extended here by
inference.

## Later integration topics

Detailed duplicate identity, update preservation, follow-up review completion,
save verification, media, recovery, and remaining target-selection details will be
documented as their walkthrough areas are reached. Image authoring/migration is
separately deferred. This is not yet a completed integration specification.
