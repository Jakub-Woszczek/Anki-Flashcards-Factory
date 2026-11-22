# Diki result recognition and lookup choices

Last updated: 2026-11-22. Status: implemented.

The browser, CLI, and HTML fetch validator share a pure result inspector in
`external_apis/diki_page.py`. It distinguishes valid source HTML from a resolved
English→Polish entry. [ADR 0007](../decisions/0007-diki-result-recognition.md)
owns the decisions; [the Diki contract](../contracts/diki.md) owns identity and
curation rules.

## Primary result and supporting evidence

The inspector retains independent signals for entry choices, spelling suggestions,
related entries, reverse-direction entries, full collocations, a negative notice,
and word-by-word fallback. The primary result follows these checks:

1. **Entries:** populated full English→Polish entries take precedence. Resolve
   exact-case, unique case-insensitive, or unique-entry identity as before.
2. **Suggestions:** Diki's explicit spelling suggestions take precedence over
   supporting related entries and word-by-word fallback.
3. **Collocation:** populated full collocation results are recognized and cached.
   Automatic translations and corpus examples are not dictionary meanings. Card
   handling for these results is still deferred.
4. **Related:** compact English→Polish related entries offer their first complete
   headword per row, in source order, without merging alternative spellings or
   Polish translations into the choices.
5. **Not found:** an explicit negative notice, word-by-word fallback, or reverse-only
   entries without the above results means no English→Polish entry was found.
6. **Unknown:** other HTML is not silently reclassified as a missing word.

Meaning lists are interpreted inside their own dictionary entity. Full entries
have headwords and populated translation rows; related `.fentry` wrappers are not
full entries. `nativeToForeignEntrySlices` identifies reverse-direction entries,
which never supply English vocabulary identity. Compact related entries are
scoped using dictionary section headings, excluding their switch-direction links.
Rows inside `wordByWordTranslation` are not related-entry choices.

For full collocations, detection uses the populated
`.collocationSearchResults .dictionaryCollocationUnits` structure, its headword,
and `.collocationUnitHeader` row. Merely mentioning collocations or showing related
collocation links does not classify a normal entry page as collocation-only.

The negative sentence is matched in result paragraphs after whitespace/case
normalization, independently of the text/link following it. The known
`.dictionaryNoResults` marker and standalone legacy negative phrases remain
recognized. The surrounding website shell is not mandatory for reduced fixtures.

## Processing and headword choices

Lookup results expose `pageKind`, `lookupQuery`, `entryChoices`, `suggestions`,
and `relatedEntries` separately. The browser labels each choice source. Related
entries use the same click-to-look-up interaction as spelling suggestions, but
they are not merged into one list.

When an entry matches the query, selection remains automatic. Otherwise a unique
entry uses its first genuine headword. When several entries remain ambiguous,
the browser and CLI offer their first headwords. A browser click sends the
original `word` query plus `headword`; the backend validates that the headword is
actually present among full English→Polish entries in the retained response and
parses only the selected headword's entries. No closest-word guess is made.

The original HTML is reused without requiring a Diki request. Missing canonical
headword snapshots are seeded for later offline translation/audio use; independent
existing canonical snapshots are retained. Drafts preserve the lookup query and
resolved identity, while source completion still concerns the original queued
occurrence. This also works for stateless marked-note lookup.

Examples:

- `back off` remains an entry despite its full collocation section.
- `lend a hand` resolves to the first headword `give somebody a hand` in its single
  full entry. Its alternative `lend somebody a hand` remains equally genuine.
- `cylinder` uses its English→Polish section, ignoring Polish→English content.
- `torta` is not found for the English→Polish workflow.
- `prologs` offers `prologue`, `prologising`, and `prologize` (the first spellings
  actually present in the saved rows).
- `take issue with sb` offers full-entry headwords; choosing
  `take issue with somebody` does not merge `take issue with something` meanings.

## Unknown-layout diagnostics

Unknown downloaded HTML retains the existing invalid-response pause and is not
saved as successful cached HTML. Explicit challenge headers/statuses still take
precedence. Recognized collocations and reverse-only pages do not trigger that
pause. Unknown cached HTML also records a diagnostic when read through the HTML
resource API; existing retained source is not automatically replaced.

Append-only JSONL diagnostics live at:

```text
ANKI_FACTORY_DATA_DIR/logs/diki-unrecognized-pages.jsonl
```

Records contain event time, query/source URL, network/cache origin, request
profile, SHA-256 digest, byte count, bounded title, and counts of known structural
markers. They exclude raw HTML, cookies, and browser-saved credentials/tokens.
An explicit custom cache root puts diagnostics beneath that root's `logs/`, so
isolated tests cannot write to the personal log. Log-write failures are reported
through Python logging without replacing the original lookup outcome.

## Evidence and verification

Reduced, credential-free fixtures come from the owner's four saved pages and the
retained `prologs`/`torta` snapshots. Additional controlled cases cover mixed
directions/collocations, absent automatic translation, word-by-word fallback,
empty/unknown structures, explicit challenges, source-preserving headword choice,
offline canonical reuse, and durable network/cache diagnostics.

Read-only inspection using the new detector accounted for all 1,045 personal
cached files: 948 entries, 39 spelling-suggestion results, 15 related-entry
results, and 43 not-found results, with no unknown files. The four owner-supplied
pages classified as entries, suggestions, not found, and collocation respectively.
This was local corpus inspection, not a live download or collection audit.

The full project check passes Ruff lint/format, Pyright, guarded offline tests,
and the frontend TypeScript/production build. See [development](../development.md)
for the verification record.
