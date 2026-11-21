# Project handbook

This handbook records the owner's intent alongside evidence from the existing
application. It is being built through a guided walkthrough; individual pages
distinguish confirmed requirements, current behavior, open decisions, and gaps.

## Start here

- [Project purpose and scope](project.md): why the project exists, goals, and constraints.
- [Feature map](features.md): capabilities, implementation state, and specification coverage.
- [Architecture](architecture.md): local deployment, components, state ownership, and known mismatches.
- [Development and verification](development.md): project-local checks, editor/hooks/CI, guarded offline tests, and explicit integration checks.
- [Walkthrough checkpoint](review.md): current question and instructions for resuming the interview.

## Rules and reference

- [Diki contract](contracts/diki.md): compatibility, selected translations, audio/examples, source policy.
- [Anki contract](contracts/anki.md): collection context, note types, refresh rules, and tags.
- [Stored-field contracts](../note-data-contracts.md): agreed field syntax and audit scope; currently only `en_word`.

## Feature explanations

- [Vocabulary queues](features/vocabulary-queues.md)
- [Existing-note refresh](features/existing-note-refresh.md)
- [Marked-note review](features/marked-note-review.md)
- [Offline cache and preparation](features/offline-cache.md)
- [LLM assistance](features/llm-assistance.md)

## Decisions and future work

- [ADR 0001: Personal workbench scope](decisions/0001-personal-workbench-scope.md)
- [ADR 0002: Per-entry vocabulary resolution](decisions/0002-per-entry-vocabulary-resolution.md)
- [ADR 0003: Retain a rolling Diki snapshot](decisions/0003-rolling-diki-snapshot.md)
- [ADR 0004: Source files are the word queues](decisions/0004-file-backed-word-queues.md)
- [ADR 0005: Diki headwords and meaningful case](decisions/0005-diki-headwords-and-case.md)
- [Roadmap and deferred discussions](roadmap.md): future ideas and open decisions.
- [Root to-do list](../to-do): recorded changes for a separate implementation session.
- [Development-history baseline](review.md#repository-evidence-baseline): recent steps and commit evidence.

## Which document owns a rule?

Use `project.md` for goals/scope, the relevant contract for integration/content
rules, feature pages for workflow purpose, and ADRs for significant decisions and
rationale. The field-contract document owns agreed parser/audit rules; a broader
compatibility goal does not silently change those parsers.

The checkpoint owns interview progress, not a competing copy of feature rules.
The roadmap explains future work; concrete change requests go into `to-do`.
Earlier `MIGRATION.md`, `plan.md`, and `research.md` provide historical context and
may describe superseded behavior. Raise conflicts rather than treating old plans
or current code as automatic approval of requirements.

For installation and operational commands, use the [README](../README.md).
The baseline walkthrough recorded behavior changes for separately authorized
implementation. It is complete; later implementation updates (including Q-001)
are recorded in the checkpoint, feature pages, ADRs, and backlog.
