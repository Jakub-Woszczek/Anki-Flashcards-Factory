import os
import google.generativeai as genai
from rich.console import Console
from rich.markdown import Markdown
from dotenv import load_dotenv


class GeminiBot:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash-lite")
        self.console = Console()

    def get_answer(self, question):
        response = self.model.generate_content(question)
        return response.text

    def get_info(self):
        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                print(m.name)

    def get_word_translation(self, word):
        print(f"Translating {word} ...")
        prompt = f"Translate word '{word}' into  Polish"
        description = self.get_answer(prompt)
        markdown_renderable = Markdown(description)
        self.console.print(markdown_renderable)
        return None

    def get_word_sentences(self, word: str, translations: list = None):
        prompt = f"Provide examples of English sentences using the word: {word}"

        if translations:
            additional_prompt = "given the translations: "
            prompt = prompt + additional_prompt + ", ".join(translations)
        response = self.get_answer(prompt)
        markdown_renderable = Markdown(response)
        self.console.print(markdown_renderable)

        return None
