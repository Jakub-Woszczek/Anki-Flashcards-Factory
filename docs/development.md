# Development and verification

Last updated: 2026-11-21.

Status: default test boundary confirmed by the owner in interview batch 21.
Legacy live tests were retired on 2026-11-19 and current discovery passes offline.
The standard check/test commands, hooks, and CI now enforce network isolation (`T-002`).

## Project-local quality tooling

Activate the project's environment, then install `requirements-dev.txt` and run
`python -m pre_commit install` once per checkout. Tool versions are pinned there;
`pyproject.toml` owns lint/format and Pyright rules, so diagnostics are reproducible
outside VS Code. The documented Python 3.11 minimum remains the static-analysis
target. CI requests an available Python `3.12` build for its macOS runner rather
than the exact local `.python-version` patch, which may not have a hosted arm64
build. The existing local environment does not need to be moved or recreated
merely for this cleanup.

```bash
python -m tools.check          # lint, format check, types, offline tests, frontend build
python -m tools.test_offline   # guarded test-only run
python -m ruff check --fix .   # reviewed safe fixes; no --unsafe-fixes
python -m ruff format .
```

The single check command runs from any working directory when the project is on
Python's import path and uses the invoking interpreter for all Python tools.
Node dependencies must already be installed with `npm --prefix frontend ci`.
The frontend build includes TypeScript checking; a separate ESLint/Prettier stack
is not introduced for this local workbench.

The 2026-11-19 full check passed: Ruff lint, formatting of 42 Python files,
Pyright with zero errors/warnings, 109 tests run (2 live checks skipped), and the
frontend production build. All configured local hooks were also exercised and passed.

The 2026-11-21 Q-001 full `python -m tools.check` passed: Ruff lint/format
(42 Python files), Pyright with zero errors/warnings, 132 offline tests run
(2 opt-in live checks skipped), and frontend TypeScript/production build.
New regressions cover live source counts, exact duplicate-line consumption,
book isolation, changed lookup spellings, concurrent CLI capture/two workspaces,
stale API requests, edits during lookup/audio preparation, legacy migration, and
restart at removal/SQLite boundaries. API checks use in-process ASGI with temporary
stores and fake integrations. No live Anki/Diki requests were used for this change.

The later 2026-11-21 headword-resolution full check also passed: Ruff lint/format
(44 Python files), Pyright with zero errors/warnings, 145 tests run (143 passed,
2 opt-in live checks skipped), and frontend TypeScript/production build. Thirteen
new regression methods cover Basel/lead-astray resolution, case-distinct entries,
ambiguity, CLI capture, cache identity/provenance, offline alias audio, old prefetch
metadata, Anki/index candidates, source-draft identity, and exact-entry completion.
Tests use temporary stores and fake integrations. The owner-requested manual live
Diki comparisons preceded implementation and are recorded separately in
[ADR 0005](decisions/0005-diki-headwords-and-case.md); no live Anki operation or
dictionary fixture refresh was performed for verification.

Local hooks check changed Python files with Ruff, then run project-wide Pyright
and guarded tests for Python changes. Frontend changes trigger its type-check/build.
Activate the development environment before committing. GitHub Actions runs the
full check on macOS for pushes and pull requests with read-only repository access.
Dependency installation requires the network; the regression tests do not.

### VS Code scope

The shared `.vscode/settings.json` applies to this workspace, overriding the user's
global Python `formatOnSave: false`. It enables Ruff formatting and safe fix/import
actions on explicit saves. It does not change settings in other repositories.
Select this project's interpreter in **Python: Select Interpreter**; the default
hint is `.venv`, while an already selected `.ankiFac` remains usable. Pylance reads
the project's `standard` Pyright configuration, including the unused-code checks.
The **Quality: all checks** task
uses that selected interpreter. Test Explorer uses direct unittest discovery;
use the quality task or guarded CLI for enforced network isolation.

### Behavior-preserving diagnostic fixes

Formatting/imports and inaccurate type annotations were cleaned up without changing
stored fields or workflows. Dynamic test doubles use explicit `Any` only at their
fixture boundaries. Production JSON settings are heterogeneous and typed accordingly.
Narrow suppressions preserve the parser's specified `ValueError`, the legacy index
error conversion, the lock-timeout exception context, and optional Gemini's broad
SDK-error-to-advisory-text behavior. A possible textless Gemini response still has
its prior rendering behavior: no fallback was specified, so the rendering argument
has a documented local type-check exception rather than an invented behavior change.

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

- The README documents the guarded full-discovery runner.
- `tests/test_diki_api.py` puts two live Diki checks behind
  `RUN_LIVE_DIKI_TESTS=1`.
- The three original live smoke tests were removed as `T-001` on 2026-11-19.
- The two read-only legacy Anki tests were also removed with the retired manual
  index-scanning workflow. Both legacy test modules are gone.
- Direct-to-folder audio-export tests were removed with the obsolete export code.
- `tools/test_offline.py` blocks socket connections and DNS for the entire discovery
  and test run. It forces live checks off and resets the application offline flag
  only within the test process, so fake download tests still execute normally.
- Guard regressions verify blocked Anki/Diki transports, restoration of environment
  overrides, and a failing run when a test accidentally attempts network access.

Routine full discovery:

```bash
python -m tools.test_offline
```

Direct `python -m unittest ...` bypasses the runner's guard. Use it deliberately for
focused checks or explicitly requested live tests. `RUN_LIVE_DIKI_TESTS=1` enables
the two live Diki tests only with direct unittest invocation, never through the
guarded runner. Offline verification means fake transport, not bypassing it.

On 2026-11-19, discovery ran 107 tests successfully with 2 opt-in live checks
skipped. A temporary process-level patch blocked `socket.socket.connect` to verify
that no real connections were attempted. The initial run with `DIKI_OFFLINE=1`
failed because it blocked mocked downloads; the successful run unset it.

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
