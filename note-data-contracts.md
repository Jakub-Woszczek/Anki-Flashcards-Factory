# Note data contracts

Incrementally defined contracts for content stored in Anki fields. These rules
are a work in progress: a violation means the content needs review, not that it
should automatically be deleted or rewritten.

## Purpose and implementation

Notes sharing an Anki note type can still contain inconsistently structured field
values. The goal is to make future Python loops parse every included field
predictably, without guessing its meaning or format.

Each field contract defines its meaning, allowed content, required/optional status,
empty-value behavior, exact encoding, parser return type and validation errors.
Parsers return predictable values or explicit errors, without silently cleaning or
rewriting content. Contract development is incremental, one field at a time.

- [note-data-contracts.md](note-data-contracts.md): agreed rules and migration checkpoint.
- [backend/note_contracts.py](backend/note_contracts.py): separate field parsers.
- [tools/audit_note_contracts.py](tools/audit_note_contracts.py): read-only audit
  against the active Anki profile through AnkiConnect.

## Scope

- `Basic [reverse+audio]`
- `Basic [reverse+audio+image]`

Excluded from all contract work, parsing and auditing:

- `Basic dikiMiss [+image]`
- `TEMP Image recall`

The parser's `NOTE_TYPES` allow-list includes only the two types above.
Only `en_word` is defined so far; other fields have no contract yet.

## Version 3: `en_word` (both included note types)

**Meaning:** One English word or phrase, stored as plain text.

**Parser:** `backend.note_contracts.parse_en_word(value) -> str`.

### Current rules

- Required, nonempty string.
- Letters `A-Z` and `a-z` are allowed; capitalization is preserved.
- At least one letter is required; punctuation alone is not a phrase.
- Hyphens (`-`), exclamation marks (`!`), periods (`.`), commas (`,`), and question
  marks (`?`) are allowed and preserved. Their placement is not checked.
- Words are separated by exactly one ordinary space (`U+0020`).
- Straight (`'`) and curly (`’`) apostrophes are allowed between letters, at the
  beginning of the entire phrase, and before a hyphen. Each apostrophe must follow
  a letter or start the phrase, and must precede a letter or hyphen. Examples:
  `don't`, `John's`, `it’s`, `'at a girl!`, and `jack-o'-lantern`.
- No leading/trailing spaces, repeated spaces, tabs, line breaks or special spaces.
- No HTML, entities, media markup, digits or punctuation other than the above.
- Apostrophes cannot end the phrase, follow spaces/hyphens/punctuation, or occur
  consecutively.

This checks syntax, not whether the text is linguistically valid English. Rules
can be revised after reviewing audit failures. Version 2 added the five allowed
punctuation characters. Version 3 also allows apostrophes at the beginning of the
phrase and before hyphens. Spacing rules and the HTML prohibition are unchanged.

### Result and failure behavior

- Valid: return the original string unchanged; no lowercasing or cleanup.
- Invalid or missing: raise `ValueError` with a reason.
- Parsing and auditing never modify notes or synchronize Anki.

Examples that pass: `apple`, `New York`, `don't give up`, `John's book`, `it’s fine`,
`well-known`, `Come on!`, `That's news to me.`, `one for all, and all for one`,
`Are we there yet?`, `'at a girl!`, `jack-o'-lantern`.

Examples that fail: an empty value, ` apple`, `two  words`, `<b>apple</b>`, `word1`,
`dogs'`, `don''t`, `...`.

### Run the audit

With Anki open and AnkiConnect enabled, run from the project root:

```bash
python -m tools.audit_note_contracts --sample-size 10
```

The command reads `.env` for the project's existing AnkiConnect configuration.
It parses every `en_word` in both included note types, prints pass/fail totals
per type and reasons, and displays at most the requested number of failing notes
(note ID, type, original field value and reason). The sample is the first failures
encountered, not a random or representative sample. Other fields are not parsed.

Exit codes: `0` = all comply, `1` = violations found, `2` = audit could not finish.

## Iteration workflow

1. The user describes or refines one field's contract, including empty values.
2. Show the Python parsing logic and update this file and the separate parser
   together. Increment `CONTRACT_VERSION` when agreed rules change.
3. Run the parser against that field in every applicable note, not just a sample.
4. Report pass/fail totals per type and only a sample of failing notes, including
   note IDs, original field contents and reasons. Do not dump all failures.
5. The user decides whether to refine the rules or plan a separate content
   migration; update the rules and repeat the audit.

Audits are read-only. Tagging, rewriting notes and changing note types are
separate, explicitly agreed operations.

## Migration

### Completed: image-only notes moved out of `en_word`

During the `en_word` audit, 44 notes in `Basic [reverse+audio+image]` contained a
labelled image in `en_word` rather than a plain-text English phrase. Their `image`
field contained a matching image with the English word hidden. Both
`pl_translation` and `audio_en` were empty in all 44 notes.

These notes were tagged `IMG_IN_EN`, preserving existing tags, then migrated to
the separate `TEMP Image recall` type using this mapping:

| Original field | New field | Meaning |
| --- | --- | --- |
| `image` | `prompt_image` | Image with the English word hidden |
| `en_word` | `answer_image` | Image with the English word visible |
| `pl_translation`, `audio_en` | Discarded | Verified empty before migration |

The existing `Karta 1` card was mapped to `Card 1`. The resulting type has one
direction only: front `{{prompt_image}}`, back `{{answer_image}}`. It is excluded
from the data contracts; do not run `parse_en_word` on its image fields.

Post-migration verification found 44 notes / 44 cards, all retaining `IMG_IN_EN`,
and exactly one image in each of `prompt_image` and `answer_image`. The previously
inspected example also retained the correct hidden/labelled image mapping.

### Last verified checkpoint

`en_word` contract version 3 is implemented. The last full audit after migration
reported:

| Included note type | Checked | Passed | Failed |
| --- | ---: | ---: | ---: |
| `Basic [reverse+audio]` | 1,886 | 1,886 | 0 |
| `Basic [reverse+audio+image]` | 380 | 380 | 0 |
| **Total** | **2,266** | **2,266** | **0** |

These counts are a historical checkpoint, not fixed expectations for future runs.

### Resume here

1. Read the current rules above and rerun the audit with Anki open:

   ```bash
   python -m tools.audit_note_contracts --sample-size 10
   ```

2. Choose the next field and follow the iteration workflow. No contracts have
   been agreed yet for:

   | Field | Applicable included note types |
   | --- | --- |
   | `pl_translation` | Both |
   | `audio_en` | Both |
   | `image` | `Basic [reverse+audio+image]` |
   | `sentences` | `Basic [reverse+audio]` |

3. Inspect actual content and agree its format and empty-value rules before
   implementing the next parser. Do not infer a contract from the field name alone.
4. Extend the auditor as each additional contract is defined. It currently
   validates only `en_word`; a successful audit does not validate other fields.
