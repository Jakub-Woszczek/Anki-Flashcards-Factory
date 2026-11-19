import tempfile
from pathlib import Path
from typing import Any

from backend.word_completion import WordCompletion


def install_completion(test, service):
    directory = tempfile.TemporaryDirectory()
    test.addCleanup(directory.cleanup)
    root = Path(directory.name)
    words = root / "words.txt"
    words.write_text("streamline\ntake\n", encoding="utf-8")
    service.completions = WordCompletion(root / "test.sqlite3", words)


class ReadBackAnki:
    note_id = 99
    call: tuple[Any, ...]

    def invoke(self, action, **_params):
        assert action == "getActiveProfile"
        return "Test profile"

    def get_note(self, note_id):
        assert note_id == self.note_id
        return {
            "noteId": note_id,
            "modelName": self.call[1],
            "fields": {name: {"value": value} for name, value in self.call[2].items()},
            "tags": self.call[3] if len(self.call) > 3 else [],
        }

    def get_note_cards(self, _note_id):
        return [{"deckName": self.call[0]}]
