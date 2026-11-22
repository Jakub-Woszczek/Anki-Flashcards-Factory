# Separate code and durable data

Last updated: 2026-11-22. Status: implemented and local migration completed.

## Configuration and ownership

The code checkout contains application code, documentation, tooling, and controlled
test fixtures. Personal runtime data lives in a separate directory/repository.
Set one required variable in the **code checkout's** ignored `.env`:

```dotenv
ANKI_FACTORY_DATA_DIR=../Anki-Flashcards-Factory-data
```

Absolute paths and `~` are supported. Relative roots resolve against the code
checkout, independent of the command's working directory. The root must exist;
missing configuration never silently creates another dataset. Normal component
directories are created as needed. Code/build paths and `.env` remain code-local.

`backend/settings.py` owns lazy path resolution. Entry points load that code-local
`.env` before resolving defaults, while already exported environment values win.
`ANKI_FACTORY_DB_PATH`, `DATABASE_PATH`, `DIKI_CACHE_DIR`, and `DIKI_WORDS_DIR` are
retired; a nonempty old setting produces an actionable error rather than competing
data locations. The optional legacy JSON index now lives at `legacy/note_index.json`
and retains its import/backup behavior when the SQLite note index is empty.

Explicit constructor paths remain available for isolated tests. Prefetch's explicit
`--words-dir` and `--cache-dir` overrides remain available; relative values now use
the data root, and absolute values are used directly. These are deliberate per-run
overrides, not additional required configuration.

## Layout and Git policy

All paths below are relative to the configured data root:

| Path | Role | Data Git policy |
| --- | --- | --- |
| `words_to_add/` | Main/book consuming queues | Track |
| `anki_flashcards_factory.sqlite3` | Workspace settings/drafts, index, save/removal recovery | Track |
| `diki_cache/html/`, `diki_cache/audio/` | Retained raw HTML and MP3 snapshots | **Track both** |
| `diki_cache/index.sqlite3` | Digests/provenance, discovery, retries, cooldowns, pacing, request history | Track |
| `archives/` | Exact source backups and historical migrations | Track |
| `backups/` | Deliberate Anki/database snapshots and split manifest | Track |
| `logs/` | Downloader logs | Ignore |
| `runtime/launchd/` | Generated machine-specific scheduler plist | Ignore |
| `.local/` | Local-only credentials/retained relay configuration | Ignore |
| Locks, SQLite transient journals, temporary writes, macOS metadata | Coordination/disposable files | Ignore |

Stop backend/capture/prefetch writers before taking a Git checkpoint or changing
the dataset's Git revision. Commit SQLite snapshots together with their related
queues/resources. The app itself does not run Git, and the data directory need not
have Git metadata to work. There is no submodule or automatic Git synchronization.

The owner specifically approved retiring the two unused `external_apis/tmp/`
recordings rather than migrating them. Virtualenvs, dependencies, compiled output,
and editor/tool caches remain disposable code-workspace artifacts. Actual Anki
collections/media remain owned by Anki, outside this split.

## Consumers

- `SessionStore`, `NotesDatabase`, and `WordCompletion` share the same default
  SQLite database. Browser discovery, CLI capture, prefetch, dashboard coverage,
  and bulk-cleanup commands share `words_to_add/`.
- `DikiResources` gives browser/CLI/background consumers the same cache directory.
  Fetch profiles, filenames, source retention, and request behavior are unchanged.
- New operational backup references in SQLite are relative to the database parent
  (`archives/...`), which is the data root for the default database. Existing
  relative source/workspace and save-entry identities remain unchanged.
- The frontend describes queues under the configured data root. It accesses data
  through backend operations rather than reading the filesystem itself.
- `tools.diki_launchd` uses the code checkout/interpreter for execution and data-root
  logs. `--install` copies the generated plist to `~/Library/LaunchAgents` without
  loading the job. See README for explicit bootstrap/bootout commands.

## Migration command

The one-time tool is independent of the new runtime configuration and defaults to
a report. Stop all writers before applying or retiring files:

```bash
python -m tools.migrate_data --destination ../Anki-Flashcards-Factory-data
python -m tools.migrate_data --destination ../Anki-Flashcards-Factory-data --apply
python -m tools.migrate_data --destination ../Anki-Flashcards-Factory-data --verify
# After verification, with original writers still stopped:
python -m tools.migrate_data --destination ../Anki-Flashcards-Factory-data --verify --retire-source
```

The destination must exist outside the code checkout. Existing destination files
are not overwritten. The tool rejects source symlinks and unfinished saves/removals,
copies **working-tree** queues byte-for-byte, snapshots SQLite consistently through
its backup API, preserves cached data/metadata, rebases active archive references,
and records SHA-256 hashes and original reference locations. It checks SQLite
integrity and every cached file against its resource digest/size. Retirement first
checks every original's hash, preserving all originals if capture changed a file.

The original application database is retained as `backups/pre-data-split.sqlite3`.
The report is `backups/data-split-manifest.json`. SQLite files, including the
historical archived database, are consistent backup-API snapshots: their logical
contents are preserved, while SQLite header/file bytes can differ. Other copied
files are byte-identical. Historical `word_list_archive.source` locations remain provenance.
Save IDs, entry IDs, session IDs, intent hashes, expected/observed payloads, and
current drafts are not rewritten. Logs/relay credentials are moved but ignored;
old generated plists/locks are retired. Only the two specifically approved deprecated
MP3 filenames are removed from `external_apis/tmp/`.

The manifest is **migration-time evidence**: normal processing changes queues and
databases, so later `--verify` can correctly fail once work has resumed. Do not
rerun `--apply` over an existing dataset. A failed partial copy is left visible for
inspection, not automatically overwritten or treated as complete.

### Rollback

Before resuming work, the manifest maps original paths to copied files and database
snapshots, and `pre-data-split.sqlite3` retains the original database references. To
restore an old code revision, stop writers, restore its original layout using that
mapping and the original database snapshot, and restore its matching configuration
and scheduler. Keep the current dataset intact while doing so. After new processing,
account for those new writes first; do not switch back to an older database/queue
snapshot and replay already-completed entries.

## Local migration evidence — 2026-11-22

- Destination: `/Users/jwdev/sidePrjs/anki/Anki-Flashcards-Factory-data`.
- Copied 1,496 existing files plus an original application-database snapshot;
  the manifest verifies 1,497 files. All copies and SQLite integrity checks passed.
- Preserved **1,037 HTML files and 437 MP3s**, including metadata digest/size checks.
- Preserved the current modified main queue: **636 nonempty entries**; book queue:
  **682**. These counts are historical migration evidence, not fixed expectations.
- Application tables retained 5 sessions, 472 indexed notes, 446 save records,
  483 legacy archived-line records, and 11 consumed source receipts. There were no
  unfinished source removals. Active backup columns contain no absolute references.
- Updated the local `.env` to the single data-root setting and retired original
  queues/data/Anki export only after copy verification. Deleted the two deprecated MP3s.
- Regenerated and installed a valid launchd plist with the current interpreter,
  checkout, and data-root logs. The job was **not loaded before migration and remains
  unloaded**; installation did not download anything.
- Controlled HTML fixtures remain with code. The guarded test runner gives discovery
  and tests a temporary data root and suppresses retired inherited path settings.
  CI needs only the code checkout. No live Diki/Anki request or collection mutation
  was used for the migration or routine verification.

See [ADR 0006](../decisions/0006-separate-data-root.md) for rationale and
[development](../development.md) for verification commands.

Full verification passed: `python -m tools.check` completed Ruff lint/format,
Pyright with zero errors/warnings, 163 tests (161 passed, 2 opt-in live checks skipped),
and frontend TypeScript/Vite production build. The final migration verification
also passed after source retirement. Durable dataset files, including all HTML/MP3,
were added to the data repository's Git index; logs, runtime files, and `.local/`
credentials were confirmed excluded. No commit or push was performed.
