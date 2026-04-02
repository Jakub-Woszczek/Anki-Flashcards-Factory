import os
from google import genai
from rich.console import Console
from rich.markdown import Markdown


class GeminiBot:
    def __init__(self):
        self.client = genai.Client()  # Lib will pick up api key automatically
        self.model = "gemini-3-flash-preview"
        self.bot_question = "Napisz jedno zdanie o jednorożcu"
        self.console = Console()

    def get_answer(self, question):
        response = self.client.models.generate_content(
            model=self.model,
            contents=question,
        )
        return response.text

    def get_word_translation(self, word):
        print(f"Tłumaczenie słowa {word} ...")
        prompt = f"Przetłumacz słowo {word} na język polski"
        description = self.get_answer(prompt)
        markdown_renderable = Markdown(description)
        self.console.print(markdown_renderable)
        return description
