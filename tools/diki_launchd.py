"""Generate a launchd agent using this Python interpreter and checkout."""

import argparse
import plistlib
import sys

from external_APIs.diki_resources import ROOT


LABEL = "com.anki-flashcards-factory.diki-prefetch"


def configuration():
    return {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "tools.diki_prefetch",
                             "--batch-size", "25", "--max-runtime", "600"],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        "StartInterval": 1800,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(ROOT / "data" / "diki-prefetch.log"),
        "StandardErrorPath": str(ROOT / "data" / "diki-prefetch-error.log"),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate the Diki background agent (does not load it)")
    parser.parse_args()
    (ROOT / "data").mkdir(exist_ok=True)
    destination = ROOT / "data" / f"{LABEL}.plist"
    destination.write_bytes(plistlib.dumps(configuration()))
    print(destination)


if __name__ == "__main__":
    main()
