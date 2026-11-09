import tempfile
import os
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import Mock

from external_APIs.dikiApi import DikiApi
from external_APIs.diki_resources import DikiResources


class TestDikiApi(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.DikiApi = DikiApi(DikiResources(self.directory.name, interval=0))

    @skipUnless(os.getenv("RUN_LIVE_DIKI_TESTS") == "1", "Live Diki requests are opt-in")
    def test_diki_possible_spellings(self):
        self.DikiApi.resources.interval = 20
        test_cases = [
            "stanch",
            "faculty",
            "broad walk",
            "eyepatch",
            "toss up",
            "naiads",
            "tranquilizer dart",
            "pat",
            "versality",
            "take",
            "taxi",
        ]
        for phrase in test_cases:
            print(f"Testing {phrase}")
            result = self.DikiApi.possible_spellings(phrase)
            print(result)

    def test_diki_audio_harness(self):
        resources = Mock()
        resources.fetch_audio.return_value = b"ID3streamline-audio"
        api = DikiApi(resources)
        with tempfile.TemporaryDirectory() as directory:
            result = api.diki_audio_harness("streamline", directory)
            self.assertTrue(result)
            self.assertEqual((Path(directory) / "streamline.mp3").read_bytes(), b"ID3streamline-audio")
            self.assertEqual(api.last_audio_path, str(Path(directory) / "streamline.mp3"))

    def test_diki_audio_harness_uses_cache_without_media_folder(self):
        self.DikiApi.audio_path = None
        self.DikiApi.resources._save("streamline", "audio", b"ID3audio", 200, "test")
        self.DikiApi.resources.offline = True
        self.assertTrue(self.DikiApi.diki_audio_harness("streamline"))
        self.assertEqual(self.DikiApi.last_audio_path,
                         str(self.DikiApi.resources.path("streamline", "audio")))

    def test_possible_spellings_parses_diki_suggestions_from_a_404_response(self):
        resources = Mock()
        resources.fetch_html.return_value = '<div class="dictionarySuggestions">Czy chodziło ci o: <a>mischief</a></div>'
        self.assertEqual(DikiApi(resources).possible_spellings("mieschief"), {"mischief"})

    @skipUnless(os.getenv("RUN_LIVE_DIKI_TESTS") == "1", "Live Diki requests are opt-in")
    def test_get_translations(self):
        self.DikiApi.resources.interval = 20
        test_cases = [
            "stanch",
            "faculty",
            "broad walk",
            "eyepatch",
            "toss up",
            "naiad",
            "tranquilizer dart",
            "pat",
        ]

        for phrase in test_cases:
            print(f"Testing {phrase}")
            print(self.DikiApi.get_translations(phrase))
