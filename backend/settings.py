import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
RETIRED_PATH_VARIABLES = (
    "ANKI_FACTORY_DB_PATH",
    "DATABASE_PATH",
    "DIKI_CACHE_DIR",
    "DIKI_WORDS_DIR",
)


def load_environment() -> None:
    load_dotenv(ROOT_DIR / ".env", override=False)


def project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT_DIR / path


def data_root() -> Path:
    retired = [name for name in RETIRED_PATH_VARIABLES if os.getenv(name)]
    if retired:
        raise ValueError(
            f"Remove retired path settings {', '.join(retired)}; use ANKI_FACTORY_DATA_DIR only"
        )
    configured = os.getenv("ANKI_FACTORY_DATA_DIR", "").strip()
    if not configured:
        raise ValueError("Set ANKI_FACTORY_DATA_DIR in the code checkout's .env")
    root = project_path(configured).resolve()
    if not root.is_dir():
        raise ValueError(f"ANKI_FACTORY_DATA_DIR must name an existing data directory: {root}")
    return root


def data_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else data_root() / path).resolve()


def database_path() -> Path:
    return data_root() / "anki_flashcards_factory.sqlite3"


def legacy_index_path() -> Path:
    return data_root() / "legacy" / "note_index.json"


def words_directory() -> Path:
    return data_root() / "words_to_add"


def configured_words_to_add_path() -> Path:
    return words_directory() / "words_to_add.txt"


def diki_cache_directory() -> Path:
    return data_root() / "diki_cache"


def logs_directory() -> Path:
    return data_root() / "logs"


def launchd_directory() -> Path:
    return data_root() / "runtime" / "launchd"
