from unittest import TestCase
from pprint import pprint
from merriamWebsterDictApi import MerriamWebsterDictApi


class TestMerriamWebsterDictApi(TestCase):
    def setUp(self):
        self.merriamWebsterDictApi = MerriamWebsterDictApi()

    def test_fetch_json(self):
        try:
            data = self.merriamWebsterDictApi.fetch_json("utter")
            print(data)
        except Exception as e:
            print(f"\033[91m{e}\033[0m")  # Red print

    def test_get_definitions_with_sentences(self):
        test_data = ["test", "car", "flawlessly", "soil"]
        test_case = test_data[3]
        data = self.merriamWebsterDictApi.get_definitions_with_sentences(test_case)

        for described_word, definition, vis_list in data:
            print(f"____ word: {described_word} ____")
            pprint(definition)
            for vis in vis_list:
                print(f"- {vis}")

    def test_get_word_described(self):
        data = self.merriamWebsterDictApi.fetch_json("flawlessly")
        word = self.merriamWebsterDictApi.get_word_described(data)
        print(word)

    def test_get_similar_phrases(self):
        data = self.merriamWebsterDictApi.fetch_json("test")
        steams = self.merriamWebsterDictApi.get_similar_phrases(data)
        print(steams)
