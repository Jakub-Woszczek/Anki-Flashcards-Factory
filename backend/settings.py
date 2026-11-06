import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


def project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT_DIR / path


def database_path() -> Path:
    configured = os.getenv("ANKI_FACTORY_DB_PATH")
    if configured:
        return project_path(configured)

    legacy = os.getenv("DATABASE_PATH")
    if legacy and Path(legacy).suffix.lower() not in {".json", ".js"}:
        return project_path(legacy)

    return ROOT_DIR / "data" / "anki_flashcards_factory.sqlite3"


def legacy_index_path() -> Path | None:
    configured = os.getenv("DATABASE_PATH")
    if not configured:
        return None

    path = project_path(configured)
    return path if path.suffix.lower() == ".json" else None


def configured_words_to_add_path() -> Path:
    return ROOT_DIR / "words_to_add.txt"


def configured_prepared_words_path() -> Path | None:
    configured = os.getenv("PREPARED_WORDS_PATH")
    return project_path(configured) if configured else None
