from unittest import TestCase

from backend.services import FactoryService


class TestQueueDiff(TestCase):
    def test_queue_diff_returns_only_changed_lines_in_separate_hunks(self):
        service = FactoryService.__new__(FactoryService)
        service.session = lambda _session_id: {
            "mode": "add",
            "queue": [{"word": "first"}, {"word": "second"}, {"word": "third"}],
        }

        result = service.queue_diff("session-1", ["first", "replacement", "third", "fourth"])

        self.assertEqual(result["savedWords"], ["first", "second", "third"])
        self.assertEqual(result["proposedWords"], ["first", "replacement", "third", "fourth"])
        self.assertEqual(len(result["hunks"]), 2)
        self.assertEqual(
            result["hunks"][0]["lines"],
            [
                {"kind": "change", "saved": "second", "proposed": "replacement"},
            ],
        )
        self.assertEqual(
            result["hunks"][1]["lines"],
            [{"kind": "add", "saved": None, "proposed": "fourth"}],
        )
