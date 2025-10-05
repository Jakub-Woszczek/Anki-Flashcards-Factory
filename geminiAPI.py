import os
import google.generativeai as genai
from rich.console import Console
from rich.markdown import Markdown

# Ustawienie klucza API z zmiennej środowiskowej
# api_key = os.getenv("GEMINI_API_KEY")
# if not api_key:
#     raise ValueError("Brak klucza API. Upewnij się, że zmienna środowiskowa 'GEMINI_API_KEY' jest ustawiona.")


class GeminBot:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash-lite")
        self.bot_question = "Napisz jedno zdanie o jednorożcu"
        self.console = Console()

    def get_answer(self, question):
        response = self.model.generate_content(question)
        return response.text

    def get_info(self):
        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                print(m.name)

    def get_word_translation(self, word):
        print(f"Tłumaczenie słowa {word} ...")
        prompt = f"Przetłumacz słowo {word} na język polski"
        description = self.get_answer(prompt)
        markdown_renderable = Markdown(description)
        self.console.print(markdown_renderable)
        return description
