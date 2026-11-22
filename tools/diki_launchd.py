"""Generate a launchd agent using this Python interpreter and checkout."""

import argparse
import plistlib
import shutil
import sys
from pathlib import Path

from backend.settings import ROOT_DIR, launchd_directory, load_environment, logs_directory

LABEL = "com.anki-flashcards-factory.diki-prefetch"


def configuration():
    return {
        "Label": LABEL,
        "ProgramArguments": [
            sys.executable,
            "-m",
            "tools.diki_prefetch",
            "--batch-size",
            "25",
            "--max-runtime",
            "600",
        ],
        "WorkingDirectory": str(ROOT_DIR),
        "RunAtLoad": True,
        "StartInterval": 1800,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(logs_directory() / "diki-prefetch.log"),
        "StandardErrorPath": str(logs_directory() / "diki-prefetch-error.log"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate the Diki background agent (does not load it)"
    )
    parser.add_argument(
        "--install", action="store_true", help="Copy to LaunchAgents without loading"
    )
    args = parser.parse_args()
    load_environment()
    logs_directory().mkdir(parents=True, exist_ok=True)
    launchd_directory().mkdir(parents=True, exist_ok=True)
    destination = launchd_directory() / f"{LABEL}.plist"
    destination.write_bytes(plistlib.dumps(configuration()))
    print(destination)
    if args.install:
        agents = Path.home() / "Library" / "LaunchAgents"
        agents.mkdir(parents=True, exist_ok=True)
        installed = agents / destination.name
        shutil.copy2(destination, installed)
        print(f"Installed {installed} (not loaded)")


if __name__ == "__main__":
    main()
