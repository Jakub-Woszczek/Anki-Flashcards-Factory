# ADR 0005: Resolve Diki headwords and preserve meaningful case

Date: 2026-11-21.

Status: Accepted and implemented following the owner's Basel/lead-astray investigation.

## Context and evidence

The browser lowercased both the lookup draft and the Anki payload. It extracted
translations without returning Diki's English headword. Consequently, imported
`Basel` became `basel`, and `lead astray` failed the exact-headword filter even
though its page contained the dictionary entry `lead somebody astray`.

Owner-requested live comparisons found:

| Queries | Observed dictionary content |
| --- | --- |
| `Basel` / `basel` | Same headwords, meanings, examples, and recordings |
| `Lead Astray` / `lead astray` | Same content; headword `lead somebody astray` |
| `US` / `us` | Same entries and order |
| `Polish` / `polish` | Same entry content, different ordering; exact-case entry first |
| `Turkey` / `turkey` | Same entry content, different ordering; exact-case entry first |

Raw HTML differed because it includes query-specific and dynamic data. These
samples do not establish that every Diki query is case-insensitive. Anki's standard
Latin-character searches are case-insensitive according to its search manual;
candidate discovery therefore does not establish case-specific note identity.

## Decision

1. Preserve query casing; normalize whitespace without lowercasing outbound searches.
2. Select a genuine Diki headword, preferring an exact-case match. Otherwise accept
   one unique case-insensitive spelling. `basel` therefore resolves to `Basel`.
3. If no headword matches and the page contains one full dictionary entry, accept
   that entry's first headword. This resolves `lead astray` to `lead somebody astray`
   and supports dictionary-provided aliases/inflections without stemming.
4. Multiple unmatched entries or multiple case-only spellings without an exact-case
   match require suggestion selection. Never choose an arbitrary first entry in
   those cases. Related phrases and generated collocations do not define identity.
5. Extract meanings and pronunciation from the selected entry only. `Polish` and
   `polish`, or `Turkey` and `turkey`, must not merge merely because their lowercase
   spellings match. Multiple genuine alternatives within one entry remain valid.
6. Use the original-cased headword for the source draft, preview, new-note English
   field, CLI capture, and subsequent Anki lookup. Source completion still consumes
   only the original queue occurrence. Existing-note refresh retains its English
   field lock; this is not a historical headword-rewrite operation.

The owner explicitly selected exact-case preference over always asking for a
choice when the input already matches one case-distinct headword.

## Cache, matching, and compatibility consequences

- HTML/audio cache query keys preserve case. Existing lowercase paths and snapshots
  remain valid. A capitalized query can reuse a lowercase snapshot only when local
  parsing finds an unambiguous, non-case-distinct resolution. No automatic refresh.
- Query aliases seed missing canonical-headword resources, retaining source metadata.
  Existing canonical snapshots remain intact. This allows prepared `lead astray`
  resources to serve `lead somebody astray` offline.
- Cached audio is reused only if its recorded source URL is advertised for the
  selected headword. Discovery version 2 reconsiders older negative results locally;
  local readiness also reinterprets old no-exact-match HTML without downloading it.
- Background list discovery and CLI capture preserve case-distinct vocabulary.
  Exact repeated spellings are still deduplicated for capture/download planning.
- The lowercase local note index remains an advisory candidate shortcut. Validate
  its hit alongside Anki search candidates, preferring exact-case English values.
  Allow a single historical case-only spelling only for a non-case-distinct entry.
  Successful saves retain actual English casing in the index's `en_word` value.
- Capitalized headwords receive a deterministic hash suffix in new Anki media
  filenames, preventing case-only filename collisions on macOS. Existing lowercase
  filenames remain unchanged; download URLs always come from Diki HTML.
- Older browser drafts without a resolved headword are looked up again on reopening.
  Source-draft edits retain the server's resolved identity and matching metadata.

The stored `en_word` syntax contract remains version 3. This implements dictionary
identity resolution, not a new syntax allow-list or complete Polish compatibility.

## Verification

Offline regressions cover source-derived Basel/lead-astray markup, controlled
case-distinct entries, ambiguity, CLI capture, cache reuse, pronunciation provenance,
prefetch, Anki candidate validation, preview/save casing, and exact source removal.
Full-check results are recorded in [development](../development.md).

Supersedes: earlier implementation assumptions that lowercasing query/draft content
is harmless. Clarifies [ADR 0002](0002-per-entry-vocabulary-resolution.md) and the
[Diki contract](../contracts/diki.md); does not supersede snapshot retention.
