import re
import requests
from pprint import pprint
from config import MERRIAM_WEBSTER_DIC_API


class MerriamWebsterDictApi:
    def __init__(self):
        self.merriam_api = MERRIAM_WEBSTER_DIC_API
        self.base_url = f"https://dictionaryapi.com/api/v3/references/learners/json/"

        if not self.merriam_api:
            raise ValueError(
                "Brak klucza API w zmiennej środowiskowej MERRIAM_WEBSTER_DIC_API"
            )

        pass

    def fetch_json(self, word: str):
        url = f"{self.base_url}{word}"
        params = {"key": self.merriam_api}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not data:
            raise EmptyResponseError(f"No data found for word: {word}")
        return data

    def get_definitions_with_sentences(self, word: str):
        """
        Returns list of tuples: (word, definition, sentences)
        """
        json_response = self.fetch_json(word)
        defs_with_sentences = []

        for definitions_struct in json_response:
            described_word = definitions_struct["hwi"]["hw"]
            definitions = definitions_struct["def"]

            # definitions = json_response[0]["def"]

            # This refers to nouns/verbs ... when word eg. "soil" is simultaneously verb and noun
            for sseq_dict in definitions:
                pprint(sseq_dict)
                sseq = sseq_dict["sseq"]

                for sense_struct in sseq:
                    sense_struct = sense_struct[0]

                    assert sense_struct[0] == "sense"
                    defining_text = sense_struct[1][
                        "dt"
                    ]  # There should be definition and verbal illustrations

                    verbal_illustrations = []
                    definition_struct, definition = None, False
                    for item in defining_text:
                        if item[0] == "text" and definition_struct is None:
                            definition_struct = item
                            definition = self.remove_tokens(definition_struct[1])
                            if not definition:
                                continue

                            # print("_____ DEFINITION _____")
                            # print(definition, end="\n")

                        if item[0] == "vis":
                            verbal_illustrations.append(item)

                    verbal_illustration_list = []
                    for verbal_illustration_struct in verbal_illustrations:
                        for verbal_illustration_dict in verbal_illustration_struct[1]:
                            verbal_illustration = self.remove_tokens(
                                verbal_illustration_dict["t"]
                            )
                            if verbal_illustration[0].isupper():
                                verbal_illustration_list.append(verbal_illustration)
                                # print("• " + verbal_illustration)
                                # print("")

                    if definition:
                        defs_with_sentences.append(
                            (described_word, definition, verbal_illustration_list)
                        )

        return defs_with_sentences

    def remove_tokens(self, text: str) -> str:
        text = re.sub(r"\[=.+?\]", "", text)
        text = re.sub(r"\{[^}]+\}", "", text)
        text.replace("  ", " ")  # Double space
        return text.strip()

    def get_word_described(self, json_struct):
        return json_struct[0]["hwi"]["hw"]

    def get_similar_phrases(self, json_struct):
        return json_struct[0]["meta"]["stems"]


class EmptyResponseError(Exception):
    """Raised when the API response body is empty"""

    pass
