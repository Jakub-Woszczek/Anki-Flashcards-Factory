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
- [Remote Diki downloader](features/remote-downloads.md)
- [Diki result recognition and lookup choices](features/diki-results.md)
- [Separate code/data storage and migration](features/data-storage.md)
- [LLM assistance](features/llm-assistance.md)
- [Maintenance, retired workflows, and quality tooling](features/maintenance-and-tooling.md)

## Decisions and future work

- [ADR 0001: Personal workbench scope](decisions/0001-personal-workbench-scope.md)
- [ADR 0002: Per-entry vocabulary resolution](decisions/0002-per-entry-vocabulary-resolution.md)
- [ADR 0003: Retain a rolling Diki snapshot](decisions/0003-rolling-diki-snapshot.md)
- [ADR 0004: Source files are the word queues](decisions/0004-file-backed-word-queues.md)
- [ADR 0005: Diki headwords and meaningful case](decisions/0005-diki-headwords-and-case.md)
- [ADR 0006: Separate data root](decisions/0006-separate-data-root.md)
- [ADR 0007: Diki result recognition and choices](decisions/0007-diki-result-recognition.md)
- [ADR 0008: Selected-entry alternatives and existing notes](decisions/0008-diki-entry-alternatives-and-existing-notes.md)
- [ADR 0009: Automatic remote preparation and immediate background import](decisions/0009-remote-preparation-scheduling.md)
- [Roadmap and deferred discussions](roadmap.md): future ideas and open decisions.
- [Loose thoughts and possible work](todo.md): the owner's pending ideas and reminders, not implementation plans.
- [Development-history baseline](review.md#repository-evidence-baseline): recent steps and commit evidence.

## Which document owns a rule?

Use `project.md` for goals/scope, the relevant contract for integration/content
rules, feature pages for workflow purpose, and ADRs for significant decisions and
rationale. The field-contract document owns agreed parser/audit rules; a broader
compatibility goal does not silently change those parsers.

The checkpoint owns interview progress, not a competing copy of feature rules.
The roadmap provides broader future-work context. `docs/todo.md` holds only the
owner's pending loose thoughts; entries are not specifications, confirmed
diagnoses, priorities, implementation plans, or authorization to implement. List
order does not imply priority. Clarify scope when the owner chooses an item.

Implemented behavior and completed work belong in the relevant `docs/features/`
page, linked from `docs/features.md`. When a thought is completed, update that
documentation and remove it from `docs/todo.md`; do not maintain a second root
todo list or a completed section in the pending list. Contracts and ADRs retain
their authority over detailed rules and decisions.

Earlier `MIGRATION.md`, `plan.md`, and `research.md` provide historical context and
may describe superseded behavior. Raise conflicts rather than treating old plans
or current code as automatic approval of requirements.

For installation and operational commands, use the [README](../README.md).
The baseline walkthrough recorded behavior changes for separately authorized
implementation. It is complete; later implementation updates (including Q-001)
are recorded in the checkpoint, feature pages, ADRs, and backlog.
