"""Explicit offline checkout-to-data-root migration. Stop all writers before applying."""

import argparse
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.settings import ROOT_DIR

MANIFEST = "backups/data-split-manifest.json"
ORIGINAL_DATABASE = "backups/pre-data-split.sqlite3"
DEPRECATED_AUDIO = ("Be my guest..mp3", "overflow.mp3")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def transient(path: Path) -> bool:
    return (
        path.name == ".DS_Store"
        or path.name.endswith((".lock", "-wal", "-shm", "-journal", ".plist"))
        or path.name.startswith((".download-", ".words-"))
    )


def inventory(source: Path) -> list[tuple[Path, Path]]:
    files = []
    for directory in ("data", "words_to_add"):
        root = source / directory
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Resolve source symlinks before migration: {path}")
            if not path.is_file() or transient(path):
                continue
            relative = path.relative_to(root)
            if directory == "words_to_add":
                target = Path(directory) / relative
            elif relative.suffix == ".log":
                target = Path("logs") / relative
            elif relative.suffix == ".env":
                target = Path(".local") / relative
            else:
                target = relative
            files.append((path, target))
    backup = source / "Backup.apkg"
    if backup.is_symlink():
        raise ValueError(f"Resolve source symlinks before migration: {backup}")
    if backup.is_file():
        files.append((backup, Path("backups/Backup.apkg")))
    return files


def readonly(path: Path):
    return closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30))


def check_pending(path: Path) -> None:
    with readonly(path) as db:
        prepared = db.execute(
            "SELECT COUNT(*) FROM source_resolutions WHERE state != 'consumed'"
        ).fetchone()[0]
        unknown = db.execute(
            "SELECT COUNT(*) FROM word_saves WHERE state IN ('pending','submitted')"
        ).fetchone()[0]
        removal = db.execute("""
            SELECT COUNT(*) FROM word_saves AS w JOIN sessions AS s
            ON json_extract(w.expected_json,'$.sourceEntry.sessionId')=s.id
            AND json_extract(w.expected_json,'$.sourceEntry.entryId')=
                json_extract(s.entry_json,'$.id')
            WHERE w.state IN ('verified','acknowledged')
        """).fetchone()[0]
    if prepared or unknown or removal:
        raise ValueError("Finish pending saves/source removals before relocating their files")


def snapshot(source: Path, target: Path) -> None:
    with readonly(source) as old, closing(sqlite3.connect(target)) as new:
        old.backup(new)
    with readonly(target) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"SQLite integrity check failed: {target}")


def rebase_backups(database: Path, destination: Path) -> list[dict[str, str]]:
    changes = []
    with closing(sqlite3.connect(database)) as db, db:
        for table, key in (("source_resolutions", "entry_id"), ("word_saves", "id")):
            for identity, original in db.execute(
                f"SELECT {key},backup_path FROM {table} WHERE backup_path IS NOT NULL"
            ).fetchall():
                path = Path(original)
                if path.parent.name != "archives":
                    raise ValueError(f"Unexpected archive reference: {original}")
                relative = Path("archives") / path.name
                if not (destination / relative).is_file():
                    raise ValueError(f"Missing referenced backup: {relative}")
                replacement = relative.as_posix()
                if original != replacement:
                    db.execute(
                        f"UPDATE {table} SET backup_path=? WHERE {key}=?",
                        (replacement, identity),
                    )
                    changes.append(
                        {"table": table, "id": identity, "original": original, "path": replacement}
                    )
    return changes


def checked_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes migration root: {relative}")
    return path


def verify(destination: Path) -> dict:
    report = json.loads((destination / MANIFEST).read_text(encoding="utf-8"))
    for entry in report["files"]:
        path = checked_path(destination, entry["path"])
        if digest(path) != entry["sha256"]:
            raise ValueError(f"Migrated file changed or failed verification: {path}")
        if path.suffix == ".sqlite3":
            with readonly(path) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError(f"SQLite integrity check failed: {path}")
    with readonly(destination / "diki_cache/index.sqlite3") as db:
        for word, kind, expected, size in db.execute(
            "SELECT word,kind,digest,size FROM resources WHERE digest IS NOT NULL"
        ):
            if kind not in {"html", "audio"}:
                raise ValueError(f"Unexpected cached resource kind: {kind}")
            key = hashlib.sha256(word.encode()).hexdigest()
            resource = (
                destination / "diki_cache" / kind / (key + (".html" if kind == "html" else ".mp3"))
            )
            if resource.stat().st_size != size or digest(resource) != expected:
                raise ValueError(f"Cached resource does not match its metadata: {resource}")
    return report


def retire_source(source: Path, destination: Path) -> None:
    report = verify(destination)
    if report["source"] != str(source):
        raise ValueError("Manifest belongs to a different source checkout")
    # Validate every original before deleting any, including the working-tree queues.
    for entry in report["files"]:
        if "source" in entry:
            path = checked_path(source, entry["source"])
            if path.exists() and digest(path) != entry["sourceSha256"]:
                raise ValueError(f"Original changed since migration; preserved: {path}")
    for entry in report["files"]:
        if "source" in entry:
            checked_path(source, entry["source"]).unlink(missing_ok=True)
    for directory in (source / "data", source / "words_to_add"):
        for path in sorted(directory.rglob("*"), reverse=True):
            if path.is_file() and transient(path):
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    for name in DEPRECATED_AUDIO:
        (source / "external_apis" / "tmp" / name).unlink(missing_ok=True)
    temporary = source / "external_apis" / "tmp"
    if temporary.is_dir() and not any(temporary.iterdir()):
        temporary.rmdir()


def migrate(source: Path, destination: Path, *, apply=False) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if (
        not destination.is_dir()
        or destination.is_relative_to(source)
        or source.is_relative_to(destination)
    ):
        raise ValueError("Use an existing data directory outside the source checkout")
    files = inventory(source)
    database = source / "data" / "anki_flashcards_factory.sqlite3"
    if not database.is_file():
        raise ValueError("Source application database is missing")
    check_pending(database)
    targets = [target.as_posix() for _, target in files] + [MANIFEST, ORIGINAL_DATABASE]
    if len(set(targets)) != len(targets):
        raise ValueError("Migration destination paths collide")
    for target in targets:
        path = checked_path(destination, target)
        if path.exists():
            raise ValueError(f"Destination already exists; nothing overwritten: {path}")
    report: dict[str, Any] = {
        "source": str(source),
        "createdAt": datetime.now(UTC).isoformat(),
        "files": [],
        "rebasedBackups": [],
    }
    if not apply:
        return {"dryRun": True, "files": len(files), "destination": str(destination)}
    original = destination / ORIGINAL_DATABASE
    original.parent.mkdir(parents=True, exist_ok=True)
    snapshot(database, original)
    for old, relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = digest(old)
        if old.suffix == ".sqlite3":
            snapshot(old, target)
        else:
            shutil.copy2(old, target)
            if digest(target) != before:
                raise ValueError(f"Copy verification failed: {old}")
        if digest(old) != before:
            raise ValueError(f"Source changed while copying; stop all writers: {old}")
        report["files"].append(
            {
                "source": old.relative_to(source).as_posix(),
                "sourceSha256": before,
                "path": relative.as_posix(),
                "sha256": digest(target),
            }
        )
    report["rebasedBackups"] = rebase_backups(
        destination / "anki_flashcards_factory.sqlite3", destination
    )
    for entry in report["files"]:
        entry["sha256"] = digest(destination / entry["path"])
    report["files"].append({"path": ORIGINAL_DATABASE, "sha256": digest(original)})
    (destination / MANIFEST).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    verify(destination)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT_DIR)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--retire-source", action="store_true")
    args = parser.parse_args()
    if args.apply and args.verify:
        parser.error("Use --apply or --verify, not both")
    if args.retire_source and not (args.apply or args.verify):
        parser.error("--retire-source requires --apply or --verify")
    source, destination = args.source_root.resolve(), args.destination.resolve()
    try:
        result = (
            verify(destination) if args.verify else migrate(source, destination, apply=args.apply)
        )
        if args.retire_source:
            retire_source(source, destination)
        count = result["files"]
        print(
            json.dumps(
                {
                    "dryRun": not (args.apply or args.verify),
                    "files": count if isinstance(count, int) else len(count),
                    "destination": str(destination),
                    "sourceRetired": args.retire_source,
                }
            )
        )
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Migration failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
