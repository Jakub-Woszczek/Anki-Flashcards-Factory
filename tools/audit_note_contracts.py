"""Read-only Anki audit: python -m tools.audit_note_contracts --sample-size 10."""

import argparse
from collections import Counter
import json
import sys

from dotenv import load_dotenv

from backend.note_contracts import CONTRACT_VERSION, NOTE_TYPES, parse_en_word
from backend.settings import ROOT_DIR
from external_APIs.ankiConnect import AnkiConnect


def audit_en_words(api, sample_size=10):
    def read(action, **params):
        result = api.invoke(action, **params)
        if result is None:
            raise RuntimeError(api.last_error or f"AnkiConnect returned no result for {action}")
        return result

    report = {
        "contract_version": CONTRACT_VERSION,
        "field": "en_word",
        "checked": 0,
        "passed": 0,
        "failed": 0,
        "by_note_type": {},
        "failure_reasons": Counter(),
        "failure_samples": [],
    }
    for model in NOTE_TYPES:
        # Exact quoted note-type searches; excluded types are never requested.
        note_ids = read("findNotes", query="note:" + json.dumps(model))
        counts = {"checked": 0, "passed": 0, "failed": 0}
        for start in range(0, len(note_ids), 250):
            batch = note_ids[start:start + 250]
            notes = read("notesInfo", notes=batch)
            if len(notes) != len(batch) or {note.get("noteId") for note in notes} != set(batch):
                raise RuntimeError("Incomplete notesInfo response; rerun the audit")
            for note in notes:
                if note.get("modelName") != model:
                    raise RuntimeError("A note changed type during the audit; rerun it")
                value = note.get("fields", {}).get("en_word", {}).get("value")
                counts["checked"] += 1
                try:
                    parse_en_word(value)
                except ValueError as error:
                    counts["failed"] += 1
                    reason = str(error)
                    report["failure_reasons"][reason] += 1
                    if len(report["failure_samples"]) < sample_size:
                        report["failure_samples"].append({
                            "note_id": note["noteId"], "note_type": model,
                            "value": value, "reason": reason,
                        })
                else:
                    counts["passed"] += 1
        report["by_note_type"][model] = counts
        for key in counts:
            report[key] += counts[key]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit en_word contracts without modifying Anki")
    parser.add_argument("--sample-size", type=int, default=10, help="Maximum failing notes to display")
    args = parser.parse_args(argv)
    if args.sample_size < 0:
        parser.error("sample-size must be nonnegative")
    load_dotenv(ROOT_DIR / ".env")
    try:
        report = audit_en_words(AnkiConnect(), args.sample_size)
    except RuntimeError as error:
        print(f"Audit failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
