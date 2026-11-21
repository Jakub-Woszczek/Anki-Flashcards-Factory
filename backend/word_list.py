"""Cooperating writers share a stable lock, including across atomic replacements."""

import fcntl
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


def normalize_word(value: str) -> str:
    return " ".join(value.lower().split())


@contextmanager
def list_lock(path: Path):
    with path.with_name(path.name + ".lock").open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_write(path: Path, content: bytes):
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".words-")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            if path.exists():
                os.fchmod(handle.fileno(), path.stat().st_mode & 0o777)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def append_word(path: Path, word: str) -> bool:
    path = path.resolve()
    with list_lock(path):
        content = path.read_bytes() if path.exists() else b""
        words = {" ".join(line.split()) for line in content.decode("utf-8-sig").splitlines()}
        if " ".join(word.split()) in words:
            return False
        separator = b"" if not content or content.endswith((b"\n", b"\r")) else b"\n"
        atomic_write(path, content + separator + word.encode("utf-8") + b"\n")
        return True
