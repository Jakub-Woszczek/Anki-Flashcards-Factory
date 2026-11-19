import os
import tempfile
from unittest import TestCase, skipUnless
from unittest.mock import Mock

from external_apis.diki_api import DikiApi
from external_apis.diki_resources import DikiResources


class TestDikiApi(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.DikiApi = DikiApi(DikiResources(self.directory.name, interval=0))
        self.addCleanup(self.DikiApi.resources.close)

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

    def test_possible_spellings_parses_diki_suggestions_from_a_404_response(self):
        resources = Mock()
        resources.fetch_html.return_value = (
            '<div class="dictionarySuggestions">Czy chodziło ci o: <a>mischief</a></div>'
        )
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
