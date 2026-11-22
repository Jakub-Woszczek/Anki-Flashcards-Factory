# ADR 0007: Recognize Diki results and keep lookup choices distinct

Date: 2026-11-22. Status: Accepted.

## Decision

- The vocabulary workflow concerns **English→Polish** entries only. Ignore
  Polish→English sections when resolving vocabulary or offering related English
  entries. A reverse-only result such as `torta` is **not found** for this workflow,
  although its response is valid Diki HTML and must not pause downloads.
- Full English→Polish entries take precedence over collocations and supporting
  content. Thus `back off`, `lend a hand`, and `cylinder` are entry results.
- Preserve ADR 0005's exact-case, unique case-insensitive, and unique-entry
  resolution. Multiple genuine alternatives within one entry are acceptable;
  unmatched unique-entry resolution uses its first headword. No edit-distance,
  stemming, or closest-word guessing is introduced.
- When several entries remain ambiguous, show their genuine headwords during
  processing and let the owner choose. The owner explicitly confirmed that an
  exact headword match should still resolve automatically. Parse only the chosen
  headword's entries, from the original retained response, without requiring a new
  Diki request. Source completion still consumes the original queue occurrence.
- Keep spelling suggestions, ambiguous full-entry choices, and related-entry
  choices separate in the result and UI. Reuse the existing click-to-look-up flow
  for related entries. For each compact related-entry row, offer its first full
  English headword (not its first whitespace-delimited token, translations, or
  all alternative spellings). `prologs` is the motivating example.
- Spelling suggestions (`Czy chodziło ci o`) take precedence over related entries
  and word-by-word fallback. Neither related nor word-by-word translations prove
  that the queried expression has an entry.
- The result notice `Nie znaleziono dokładnego tłumaczenia wpisanej frazy.`, the
  word-by-word notice/container (`Poniżej prezentujemy tłumaczenia poszczególnych
  wyrazów.`), and reverse-only content establish no English→Polish entry when no
  full English→Polish entry exists. Available choices remain available separately.
- Recognize populated collocation results structurally. Automatic translation is
  optional: cached `cylinder` has `top hat` collocation content without that block;
  `Divert off` has it. Collocation translation/card handling remains undecided.
- Keep underlying evidence as independent signals, with a primary result for the
  workflow. Unknown layouts stay unknown, rather than becoming missing words.
  Record unknown responses and cached-source encounters in a durable local JSONL
  diagnostic log, including query, source, digest, time, and structural evidence.
  Do not log raw HTML, cookies, or browser-saved tokens. Retain the existing
  challenge/status handling and unknown-response pause.

## Evidence

The owner supplied browser-saved `take`, `briben`, `aoifnesfl`, and `Divert off`
pages. Local inspection also covered all 1,045 retained HTML files: 948 contain
full English→Polish entries, 84 of those also have full collocation results,
39 have spelling suggestions, 96 have a negative notice, 58 have word-by-word
fallback, and 41 have full Polish→English entries (only `torta` is reverse-only).
69 negative-result files also contain compact related entries. These are file
counts, not mutually exclusive categories or a claim about every Diki layout.

Clarifies ADR 0005 and the Diki contract. The first-alternative rule was already
accepted; this decision does not reopen it. See the implementation feature page
for current verification and fixtures.
