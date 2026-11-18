# Development and verification

Last updated: 2026-11-17.

Status: default test boundary confirmed by the owner in interview batch 21.
The intended boundary is not yet enforced across all existing test discovery;
separation work is recorded as `T-002` for another implementation session.

## Routine automated tests — accepted boundary

- Run offline using saved Diki HTML/fixtures and fake Anki responses.
- Do not contact the real Anki application, even for read-only inspection.
- Do not change the owner's actual Anki collection.
- Real Diki/Anki checks are separate, explicitly invoked integration checks.

The existing isolated tests use temporary files/databases for mutable test state.
The reusable personal Diki dataset supports collection/refinement work, but normal
code verification should not require a live personal collection or download its
inputs on demand.

## Explicit integration checks and collection audits

An intentionally invoked live check may use a running Anki instance or an external
service. Keep its purpose separate from routine offline verification.

The existing field audit is such an explicit command: it reads the active Anki
profile and currently checks only `en_word` syntax. Future compatibility checks
may combine real note reads with retained cached Diki HTML. They do not become
ordinary isolated unit tests merely because their dictionary data is local.

See [stored-field contracts](../note-data-contracts.md) and
[cache dataset goals](features/offline-cache.md). Dictionary checks use the
accepted snapshot policy; failing assertions do not authorize silent source refresh
or rewriting expectations/content.

## Current test organization and gaps

- The README documents a selected fixture/mock-backed module suite.
- `tests/test_dikiApi.py` already puts two live Diki checks behind
  `RUN_LIVE_DIKI_TESTS=1`.
- Three original live smoke tests are approved for deletion as `T-001`; they are
  still present pending separate cleanup.
- Other methods in `tests/test_ankiConnect.py` read the configured real Anki
  application without an explicit integration-test gate. Read-only is still live
  and therefore outside the accepted default boundary.
- Unrestricted discovery does not currently enforce the intended separation.
  `T-002` records that gap without choosing a test framework or gating mechanism.

No test code or integration gates were changed during this documentation batch.

## Verified isolated selection

For the deck-preservation correction committed as `60cdb9f`, this command passed
65 tests using fakes and temporary storage:

```bash
python -m unittest tests.test_word_completion tests.test_target_selection tests.test_review_stateless tests.test_diki_resources tests.test_audio_sync tests.test_sync_rate_limit
```

Those checks include original-deck preservation, sibling cards in different decks,
read-back/recovery before source cleanup, offline resource behavior, and sync
throttling. This is a recorded focused result, not a fresh whole-project test or a
live Anki/Diki compatibility audit.

Use the [README](../README.md#weryfikacja-bez-sieci) for the broader documented
offline selection. Current behavior and verification evidence remain separate
from desired feature contracts.

## Working during the handbook walkthrough

Read [the checkpoint](review.md) before continuing the interview. Record requested
behavior changes in [to-do](../to-do); implementation happens separately. Tests,
application code, and collection data are not changed just because a new intended
rule has been documented.
