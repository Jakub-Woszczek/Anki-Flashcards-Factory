"""Run the same read-only source checks locally and in CI: python -m tools.check."""

import subprocess
import sys

from backend.settings import ROOT_DIR


def main() -> int:
    commands = [
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [sys.executable, "-m", "pyright", "--pythonpath", sys.executable],
        [sys.executable, "-m", "tools.test_offline"],
        ["npm", "--prefix", "frontend", "run", "build"],
    ]
    for command in commands:
        print(f"\n> {' '.join(command)}", flush=True)
        result = subprocess.run(command, cwd=ROOT_DIR, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
