from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import requests

from external_APIs.dikiApi import DikiApi, parse_meanings, parse_translations


class TestDikiMeanings(TestCase):
    def setUp(self):
        self.html = (Path(__file__).parent / "diki_cases" / "take.html").read_text(encoding="utf-8")

    def test_examples_belong_to_their_meaning_and_exclude_additional_sentences(self):
        meanings = parse_meanings(self.html, " TAKE ")
        self.assertEqual(len(meanings), 4)
        self.assertEqual(meanings[0], {
            "translations": ["brać", "zabierać"],
            "examples": [
                {"english": "Take my hand and say that you love me.",
                 "polish": "Weź mnie za rękę i powiedz, że mnie kochasz."},
                {"english": "I'll take the dog for a walk.", "polish": "Wezmę psa na spacer."},
            ],
        })
        self.assertEqual(meanings[1]["examples"], [
            {"english": "I decided to take the job.", "polish": "Zdecydowałem się wziąć tę pracę."},
        ])
        self.assertEqual(meanings[2]["examples"], [])
        self.assertEqual(len(meanings[3]["examples"]), 1)
        self.assertEqual(sum(len(meaning["examples"]) for meaning in meanings), 4)

    def test_translation_only_contract_is_preserved(self):
        expected = [
            ["brać", "zabierać"], ["przyjmować", "akceptować"],
            ["zabierać", "podwozić (np. kogoś do domu)"], ["ujęcie (podczas kręcenia filmu)"],
        ]
        self.assertEqual(parse_translations(self.html, "take"), expected)
        response = Mock(text=self.html)
        with patch("external_APIs.dikiApi.requests.get", return_value=response) as get:
            self.assertEqual(DikiApi().get_translations("take"), expected)
        get.assert_called_once()

    def test_meaning_lookup_fetches_once_and_handles_request_errors(self):
        with patch("external_APIs.dikiApi.requests.get", return_value=Mock(text=self.html)) as get:
            self.assertEqual(DikiApi().get_meanings("take"), parse_meanings(self.html, "take"))
        get.assert_called_once()
        with patch("external_APIs.dikiApi.requests.get", side_effect=requests.Timeout):
            self.assertEqual(DikiApi().get_meanings("take"), [])
            self.assertEqual(DikiApi().get_translations("take"), [])

    def test_nested_text_and_missing_translation(self):
        html = '''<div class="dictionaryEntity"><div class="hws"><span class="hw">take</span></div>
        <ol class="foreignToNativeMeanings"><li><span class="hw">brać</span>
        <div class="exampleSentence">Take <b>my hand</b> &amp; go.
          <span class="exampleSentenceTranslation">(Weź <b>mnie</b> (teraz) za rękę.)</span>
        </div><div class="exampleSentence">Take care!</div>
        </li></ol></div>'''
        self.assertEqual(parse_meanings(html, "take")[0]["examples"], [
            {"english": "Take my hand & go.", "polish": "Weź mnie (teraz) za rękę."},
            {"english": "Take care!", "polish": ""},
        ])
        self.assertEqual(parse_meanings(html, "take it"), [])
