import os
import json
import tkinter as tk
from tkinter import messagebox
from rich.console import Console

from allNotesDb import NotesDatabase
from dikiApi import DikiApi
from ankiConnect import AnkiConnect
from geminiAPI import GeminiBot
from merriamWebsterDictApi import MerriamWebsterDictApi


class CasualNotesImprovement:
    def __init__(self):
        self.anki = AnkiConnect()
        self.diki_api = DikiApi()
        self.db = NotesDatabase()
        self.bot = GeminiBot()
        self.merriamDict = MerriamWebsterDictApi()
        self.console = Console()

        self.current_index = 0
        self.notes_to_change = []
        self.root = None
        self.label_word = None

    def addSentencesToAlreadyCreated(self):
        """Main method – loads notes and opens GUI"""
        try:
            with open(r"other/temp.json", "r", encoding="utf-8") as f:
                self.notes_to_change = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            messagebox.showerror("Error", "Nie udało się wczytać pliku other/temp.json")
            return

        if not self.notes_to_change:
            messagebox.showinfo("Info", "Brak słów do przetworzenia.")
            return

        # --- Tworzymy GUI ---
        self.root = tk.Tk()
        self.root.title("Casual Notes Improvement")
        self.root.geometry("350x250")

        # Etykieta pokazująca aktualne słowo
        self.label_word = tk.Label(self.root, text="", font=("Arial", 16, "bold"))
        self.label_word.pack(pady=15)

        # Przycisk 1: GPT
        btn1 = tk.Button(self.root, text="GPT", command=self.action_gpt, width=20)
        btn1.pack(pady=5)

        # Przycisk 2: Definicje i przykłady
        btn2 = tk.Button(self.root, text="Def & Vis", command=self.action_definitions, width=20)
        btn2.pack(pady=5)

        # Przycisk 3: Następne słowo
        btn3 = tk.Button(self.root, text="Move on →", command=self.next_word, width=20)
        btn3.pack(pady=15)

        # Pokaż pierwsze słowo
        self.show_current_word()

        self.root.mainloop()

    # --- FUNKCJE PRZYCISKÓW ---

    def show_current_word(self):
        """Wyświetla bieżące słowo w GUI"""
        if 0 <= self.current_index < len(self.notes_to_change):
            self.current_id = self.notes_to_change[self.current_index]
            self.current_word = self.anki.get_content(self.current_id)
            self.label_word.config(text=self.current_word)
            self.console.print(f"[bold cyan]Current word:[/bold cyan] {self.current_word}")
        else:
            messagebox.showinfo("Done", "To już wszystkie słowa!")
            self.root.destroy()

    def action_gpt(self):
        """Pobiera przykładowe zdania z GeminiBot"""
        if not self.current_word:
            return
        try:
            sentences = self.bot.get_word_sentences(self.current_word)
            self.console.print(sentences)
        except Exception as e:
            self.console.print(f"[red]Błąd w GPT akcji:[/red] {e}")

    def action_definitions(self):
        """Pobiera definicje i przykłady z Merriam-Webster"""
        if not self.current_word:
            return
        try:
            response = self.merriamDict.get_definitions_with_sentences(self.current_word)
            if not response:
                self.console.print("[yellow]Brak wyników[/yellow]")
                return

            if isinstance(response[0], tuple):
                for word, definition, vis in response:
                    self.console.print(f"\n _____ [bold blue]{word}[/bold blue] _____ ")
                    self.console.print(f"[italic]{definition}[/italic]")
                    if vis:
                        self.console.print("[yellow]Przykłady:[/yellow]")
                        for sentence in vis:
                            self.console.print(f"{sentence}", style="dim")
            else:
                for word in response:
                    self.console.print(word)

        except Exception as e:
            self.console.print(f"[red]Błąd w definicjach:[/red] {e}")

    def next_word(self):
        """Przechodzi do następnego słowa"""
        self.current_index += 1
        self.show_current_word()


# --- TEST ---
if __name__ == "__main__":
    app = CasualNotesImprovement()
    app.addSentencesToAlreadyCreated()
