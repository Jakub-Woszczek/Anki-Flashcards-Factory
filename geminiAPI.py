import os
import google.generativeai as genai
from rich.console import Console
from rich.markdown import Markdown


class GeminiBot:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash-lite")
        self.bot_question = "Napisz jedno zdanie o jednorożcu"
        self.console = Console()

    def get_answer(self, question):
        response = self.model.generate_content(question)
        return response.text

    def get_word_translation(self, word):
        print(f"Tłumaczenie słowa {word} ...")
        prompt = f"Przetłumacz słowo {word} na język polski"
        description = self.get_answer(prompt)
        markdown_renderable = Markdown(description)
        self.console.print(markdown_renderable)
        return description
