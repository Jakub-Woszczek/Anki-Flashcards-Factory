import os
from google import genai
from rich.console import Console
from rich.markdown import Markdown


class GeminiBot:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client()
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

    def get_word_translation(self, word):
        print(f"Tłumaczenie słowa {word} ...")

        description = self.get_answer(f"Przetłumacz słowo {word} na język polski")
        if description == "no api key provided":
            print(description)
            return description

        markdown_renderable = Markdown(description)
        self.console.print(markdown_renderable)
        return description
