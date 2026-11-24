import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    data_dir: Path
    token: str
    requests_per_day: int = 400
    work_seconds_per_day: int = 3600
    batch_seconds: int = 180
    batch_words: int = 10
    pending_bytes: int = 128 * 1024 * 1024
    min_free_bytes: int = 32 * 1024 * 1024
    max_jobs: int = 20000
    max_attempts: int = 5
    poll_seconds: int = 60
    require_mount: bool = True

    def validate(self):
        self.data_dir = Path(self.data_dir).expanduser()
        if not self.data_dir.is_absolute():
            raise ValueError("Use a dedicated absolute data directory")
        self.data_dir = self.data_dir.resolve()
        if self.data_dir == Path("/"):
            raise ValueError("Use a dedicated absolute data directory")
        if not 32 <= len(self.token) <= 256 or any(not 33 <= ord(c) <= 126 for c in self.token):
            raise ValueError(
                "REMOTE_API_TOKEN must contain 32–256 printable ASCII characters without spaces"
            )
        for value in (
            self.requests_per_day,
            self.work_seconds_per_day,
            self.batch_seconds,
            self.batch_words,
            self.pending_bytes,
            self.poll_seconds,
            self.max_jobs,
            self.max_attempts,
        ):
            if type(value) is not int or value <= 0:
                raise ValueError("Remote resource limits must be positive integers")
        if self.pending_bytes < 15 * 1024 * 1024 or self.min_free_bytes < 0:
            raise ValueError("Storage must fit at least one maximum-size HTML/MP3 pair")
        if min(self.batch_seconds, self.work_seconds_per_day) <= 15:
            raise ValueError("Worker runtime budgets must exceed the 15-second request allowance")
        if self.require_mount and not persistent_mount(self.data_dir):
            raise ValueError(
                "Mount a persistent volume at REMOTE_DATA_DIR; local testing can set REMOTE_ALLOW_EPHEMERAL=1"
            )
        return self

    @classmethod
    def from_env(cls):
        return cls(
            data_dir=Path(os.getenv("REMOTE_DATA_DIR", "/data")),
            token=os.getenv("REMOTE_API_TOKEN", ""),
            requests_per_day=int(os.getenv("REMOTE_REQUESTS_PER_DAY", "400")),
            work_seconds_per_day=int(os.getenv("REMOTE_WORK_SECONDS_PER_DAY", "3600")),
            batch_seconds=int(os.getenv("REMOTE_BATCH_SECONDS", "180")),
            batch_words=int(os.getenv("REMOTE_BATCH_WORDS", "10")),
            pending_bytes=int(os.getenv("REMOTE_MAX_PENDING_MB", "128")) * 1024 * 1024,
            poll_seconds=int(os.getenv("REMOTE_POLL_SECONDS", "60")),
            require_mount=os.getenv("REMOTE_ALLOW_EPHEMERAL") != "1",
        ).validate()


def persistent_mount(directory):
    if directory.is_mount():
        return True
    # Linux bind mounts may share a device with their parent; inspect mountinfo.
    try:
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            mount = Path(line.split()[4].replace("\\040", " ").replace("\\134", "\\"))
            if mount != Path("/") and directory.is_relative_to(mount):
                return True
    except (OSError, IndexError):
        pass
    return False
