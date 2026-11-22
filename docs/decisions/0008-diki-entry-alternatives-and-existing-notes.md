# ADR 0008: Match existing Anki notes by selected-entry alternatives

Date: 2026-11-22. Status: Accepted and implemented.

## Motivating case: anesthetic / anaesthetic

The owner reported this processing result:

| Concept | Observed/reported value |
| --- | --- |
| Original queue occurrence | `Anesthetic` |
| Resolved Diki spelling displayed by the app | `anesthetic` |
| English spelling already in Anki, reported by the owner | `anaesthetic` |
| Incorrect app result | **New note** |
| Diki headwords in the same full English→Polish entity | `anaesthetic` (BrE), then `anesthetic` (AmE) |
| Shared translation groups | `środek znieczulający`; `znieczulający` |

Read-only inspection of retained HTML confirmed both genuine headwords in the
same `.dictionaryEntity > .hws`, with the noun and adjective meaning lists in
that entity. No live Anki read was performed to verify the owner's collection
report, and no collection mutation, fuzzy-pair audit, or new Diki request was used.

Retained-source provenance at investigation time:

- Source URL: `https://www.diki.pl/slownik-angielskiego?q=anesthetic`.
- Data-relative HTML path:
  `diki_cache/html/e3d936b1cf5bccfd2138be11560c093eaff1c9130dc8e13b313af15238bb061e.html`.
- Source-content SHA-256:
  `a7ed5189c81aefb5dd17f22a5f3ecf28d0d0264f093a054d9886f065f0363d2e`.
- The capitalized query key `Anesthetic` retained the same content digest.
- The credential-free reduced regression is
  `tests/diki_cases/anaesthetic-variants.html`; its digest differs intentionally
  because website chrome, scripts, extra sentences, and related rows are omitted.
  Routine tests require only this controlled fixture, not the personal dataset.

## Cause

Exact-query resolution correctly selected the genuine headword `anesthetic`.
The lookup result then retained only that spelling for Anki matching. Searching
`anesthetic` did not discover `anaesthetic`, and the update guard would also have
rejected the alternate spelling as a different English word. Thus changing only
the lookup search would not have made the refresh path work.

## Decision

1. **Separate selected spelling from entry identity.** Keep ADR 0005/0007's
   resolution rules. For existing-note matching, retain every genuine headword
   from the selected full English→Polish entry/entries, in Diki order, deduplicated.
   Related phrases, spelling suggestions, collocations, and unselected entries
   are not identity alternatives. Do not infer equivalence from edit distance.
2. **Search first headword first.** For the motivating case, search `anaesthetic`
   first and `anesthetic` only if no valid existing note matches the first.
   The first matching spelling wins even when the resolved spelling also exists.
   The owner considers duplicate variant notes absent and will handle any such
   collection case manually; this adds no duplicate-note chooser or merge.
3. **Preserve case safeguards per alternative.** Within each headword search,
   prefer exact case; retain the existing unambiguous historical case-only
   fallback only where Diki does not distinguish that alternative's case.
   A non-case-distinct selected word can have a case-distinct alternative, so
   a single boolean on the selected spelling is insufficient. Validate actual
   Anki fields; index hits and case-insensitive Anki searches are candidates only.
4. **Allow an in-place refresh across verified alternatives.** Keep the existing
   note ID, its English field, its model restriction, and its card decks. Keep
   existing audio if refreshed audio is unavailable. The UI identifies the stored
   English spelling and previews/diffs show that English remains unchanged.
5. **Keep identity metadata authoritative.** Lookup stores `matchingHeadwords`
   alongside `lookupQuery` and `resolvedWord`; draft edits preserve those
   server-owned fields. Before an alternative-aware save, rederive the identity
   from retained Diki HTML, including for client-held stateless-review drafts.
   Client-supplied alias lists do not authorize an unrelated update.
6. **Retain source/recovery identity.** Consume only the original current source
   occurrence. Alternative-aware save intents include the matching headwords and
   selected existing note ID, so different update targets do not share an intent.
   Exact read-back of the preserved English field/deck mapping still governs
   update confirmation and recovery. Old journal payloads are not rewritten.
7. **Keep the note index coherent.** Index the actual stored English spelling,
   normalized for the key and case-preserving for the value. Do not write an
   `anesthetic` alias key pointing to an `anaesthetic` value. Searching all genuine
   alternatives provides reuse without a new index schema or alias registry.
8. **Re-evaluate old drafts without losing work.** On reopening a resolved add
   draft without matching metadata, re-run identity/matching while preserving
   translation selections, tags, flag, and one-card target. No re-resolution to
   the first spelling is forced. Ordinary creation also rechecks alternatives
   before `addNote` if an existing note appeared after lookup; unavailable alias
   searches are reported rather than interpreted as a new word.

## Expected outcome

`Anesthetic` still resolves to `anesthetic`. An existing `anaesthetic` note now
produces **Existing note found**. Refresh updates that same note's Polish content
while English remains `anaesthetic`; only the original `Anesthetic` source
occurrence completes. If no alternative exists in Anki, new-note spelling follows
the existing resolution rules.

See [existing-note refresh](../features/existing-note-refresh.md#alternative-headword-matching)
for implementation and verification. Clarifies ADR 0005/0007 and the Diki/Anki
contracts without changing the stored `en_word` syntax contract.
