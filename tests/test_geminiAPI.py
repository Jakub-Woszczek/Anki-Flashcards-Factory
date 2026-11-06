from unittest import TestCase
from external_APIs.geminiAPI import GeminiBot


class TestGeminiBot(TestCase):
    def test_word_translation_prompt_includes_diki_meaning_groups(self):
        prompt = GeminiBot.word_translation_prompt(
            "streamline",
            [["usprawniać", "optymalizować"], ["opływowy"]],
        )

        self.assertEqual(
            prompt,
            'Przetłumacz angielskie słowo "streamline" na polski.\n\n'
            "Diki podaje następujące tłumaczenia, pogrupowane według znaczeń:\n"
            "1. usprawniać, optymalizować\n2. opływowy",
        )

    def test_word_translation_prompt_omits_diki_section_without_meanings(self):
        self.assertEqual(
            GeminiBot.word_translation_prompt("mieschief", []),
            'Przetłumacz angielskie słowo "mieschief" na polski.',
        )
