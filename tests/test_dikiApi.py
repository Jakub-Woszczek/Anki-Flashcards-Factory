import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from external_APIs.dikiApi import DikiApi


class TestDikiApi(TestCase):
    def setUp(self):
        self.DikiApi = DikiApi()

    def test_diki_possible_spellings(self):
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
        missing = Mock(ok=False)
        audio = Mock(ok=True, content=b"streamline-audio")
        with tempfile.TemporaryDirectory() as directory:
            with patch("external_APIs.dikiApi.requests.get", side_effect=[missing, missing, missing, audio]) as get:
                result = self.DikiApi.diki_audio_harness("streamline", directory)

            self.assertTrue(result)
            self.assertEqual(
                [call.args[0] for call in get.call_args_list],
                [
                    "https://www.diki.pl/images-common/en/mp3/streamline.mp3",
                    "https://www.diki.pl/images-common/en/mp3/streamline-v.mp3",
                    "https://www.diki.pl/images-common/en/mp3/streamline-n.mp3",
                    "https://www.diki.pl/images-common/en-ame/mp3/streamline.mp3",
                ],
            )
            self.assertEqual((Path(directory) / "streamline.mp3").read_bytes(), b"streamline-audio")
            self.assertEqual(self.DikiApi.last_audio_path, str(Path(directory) / "streamline.mp3"))

    def test_diki_audio_harness_reports_missing_media_folder(self):
        self.DikiApi.audio_path = None

        self.assertFalse(self.DikiApi.diki_audio_harness("streamline"))
        self.assertEqual(self.DikiApi.last_error, "ANKI_MEDIA_FOLDER_PATH is not configured")

    def test_possible_spellings_parses_diki_suggestions_from_a_404_response(self):
        response = Mock(
            status_code=404,
            text='<div class="dictionarySuggestions">Czy chodziło ci o: <a>mischief</a></div>',
        )
        with patch("external_APIs.dikiApi.requests.get", return_value=response):
            self.assertEqual(self.DikiApi.possible_spellings("mieschief"), {"mischief"})
        response.raise_for_status.assert_not_called()

    def test_get_translations(self):
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
