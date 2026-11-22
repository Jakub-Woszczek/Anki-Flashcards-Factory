# ADR 0006: Separate code from a single configured data root

Date: 2026-11-22. Status: accepted and implemented.

## Context

Vocabulary files changed in code commits, while caches, SQLite state, and backups
were scattered across ignored locations inside the checkout. Independent path
settings could also make capture/browser processing and prefetch use different lists.
The owner wants separate code/data repositories with just one data-location setting.

## Decision

- Require `ANKI_FACTORY_DATA_DIR` in the code-local environment for default data access.
  Resolve relative values against the code checkout. Do not fall back to code-local data.
- Derive all normal runtime paths from this root. Retire per-component path environment
  variables; keep explicit constructor/per-run overrides for tests and targeted tooling.
- Version all durable data in the data repository, explicitly including retained HTML,
  MP3, both SQLite databases, queues, and deliberate backups. Ignore credentials,
  logs, transient locks/journals, and generated machine-specific scheduler files.
- Keep controlled parser fixtures with code so CI remains independent of personal data.
- Store new operational archive references relatively. Preserve source-entry/save
  identities and historical provenance during the explicit offline migration.

## Rationale and consequences

One root prevents consumer divergence and makes relocation a configuration change.
The code consumes a directory, not a Git API or submodule. Dataset changes are reviewed
and versioned separately. Binary SQLite snapshots require consistent checkpoints
with writers stopped; Git is not a live database merge/synchronization mechanism.

This changes data placement, not file-backed queue authority, Diki snapshot policy,
Anki field contracts, or the local-Mac operating scope. Generated launchd files must
be regenerated after moving code/data/interpreters because they contain absolute paths.

See [implemented layout and migration evidence](../features/data-storage.md).

Supersedes: project-local default data placement and independent data-path environment
overrides. Does not supersede ADRs 0001–0005.
