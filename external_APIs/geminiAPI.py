import os
from google import genai
from rich.console import Console
from rich.markdown import Markdown


class GeminiBot:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None  # No client if key missing

        self.model = "gemini-3-flash-preview"
        self.bot_question = "Napisz jedno zdanie o jednorożcu"
        self.console = Console()

    def get_answer(self, question):
        if not self.client:
            return "no api key provided"

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=question,
            )
            return response.text
        except Exception as e:
            return f"error: {str(e)}"

    @staticmethod
    def word_translation_prompt(word: str, diki_translations: list[list[str]]) -> str:
        diki_context = "\n".join(
            f"{index}. {', '.join(group)}"
            for index, group in enumerate(diki_translations, start=1)
            if group
        )
        if not diki_context:
            return f'Przetłumacz angielskie słowo "{word}" na polski.'
        return (
            f'Przetłumacz angielskie słowo "{word}" na polski.\n\n'
            "Diki podaje następujące tłumaczenia, pogrupowane według znaczeń:\n"
            f"{diki_context}"
        )

    def get_word_translation(self, word: str, diki_translations: list[list[str]]):
        print(f"Tłumaczenie słowa {word} ...")

        description = self.get_answer(self.word_translation_prompt(word, diki_translations))
        if description == "no api key provided":
            print(description)
            return description

        markdown_renderable = Markdown(description)
        self.console.print(markdown_renderable)
        return description
