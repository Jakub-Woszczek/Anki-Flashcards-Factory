from PIL.ImImagePlugin import split
from click import style
from diki_translate import Diki
import tkinter as tk
from tkinter import ttk
from rich.console import Console
from ankiConnect import AnkiConnect
from dikiApi import DikiApi
from geminiAPI import GeminiBot
from allNotesDb import NotesDatabase
from merriamWebsterDictApi import MerriamWebsterDictApi


class FlashcardApp:
    def __init__(self, path, deck):
        self.translation_vars = []
        self.tree_frame = None
        self.gemini_bot = GeminiBot()
        self.words_to_add = []
        self.diki_api = Diki("english")
        self.my_diki_api = DikiApi()
        self.anki_api = AnkiConnect()
        self.notes_db = NotesDatabase()
        self.deck = deck
        self.appConsole = FlashcardAppConsole()
        self.sentences = []

        self.root = tk.Tk()
        self.root.title("Konstruktor fiszek")
        self.root.geometry("800x600")

        # Content i przygotowanie
        self.load_words(path)
        if not self.words_to_add:
            print("Brak słówek w pliku")
            self.root.destroy()
        self.current_word = self.words_to_add.pop(0)

        # --- ramki główne ---
        footer = ttk.Frame(self.root)
        footer.pack(side="top", fill="x")

        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True)

        self.frame_left = ttk.Frame(main_frame, width=350)
        self.frame_left.pack(side="left", fill="y", padx=10, pady=10)

        self.frame_right = ttk.Frame(main_frame)
        self.frame_right.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        # --- lewa kolumna ---
        self.lbl_words_left = ttk.Label(self.frame_left, text="", font=("Arial", 10))
        self.lbl_words_left.pack(anchor="w", pady=5)
        self.set_words_left()

        self.lbl_word = ttk.Label(self.frame_left, text="", font=("Arial", 24, "bold"))
        self.lbl_word.pack(anchor="center", pady=20)
        self.set_word()

        # startowe drzewo
        self.create_tree()

        # --- stopka ---
        btn_add = ttk.Button(
            footer, text="Dodaj fiszkę", command=lambda: self._on_add()
        )
        btn_add.pack(side="left", padx=10, pady=10)

        btn_gpt = ttk.Button(
            footer,
            text="GPT translation",
            command=lambda: self._on_description_request(),
        )
        btn_gpt.pack(side="left", padx=10, pady=10)

        btn_gemini_sentences = ttk.Button(
            footer,
            text="Gemini sentences",
            command=lambda: self._on_sentences_request(),
        )
        btn_gemini_sentences.pack(side="left", padx=10, pady=10)

        btn_get_definition_and_vis = ttk.Button(
            footer,
            text="Def & vis",
            command=lambda: self._on_def_and_vis_request(),
        )
        btn_get_definition_and_vis.pack(side="left", padx=10, pady=10)

        self.image_val = tk.IntVar(footer, value=0)
        btn_image = ttk.Checkbutton(footer, text="Image", variable=self.image_val)
        btn_image.pack(side="right", padx=10, pady=10)

        self.error_val = tk.IntVar(footer, value=0)
        btn_error = ttk.Checkbutton(footer, text="Error", variable=self.error_val)
        btn_error.pack(side="right", padx=10, pady=10)

        self.gemini_diff_val = tk.IntVar(
            footer, value=0
        )  # Indicates whether gemini has different translation
        btn_gemini_diff = ttk.Checkbutton(
            footer, text="Gemini Diff", variable=self.gemini_diff_val
        )
        btn_gemini_diff.pack(side="right", padx=10, pady=10)

        self.to_edit_val = tk.IntVar(
            footer, value=0
        )  # Indicates whether gemini has different translation
        btn_edit_val = ttk.Checkbutton(
            footer, text="To-edit", variable=self.to_edit_val
        )
        btn_edit_val.pack(side="right", padx=10, pady=10)

        self.sentences_label = tk.Label(text="Write sentences (seperated by $ sign)")
        self.sentences_label.pack()
        self.sentences_entry = tk.Text(width=40, height=8)
        self.sentences_entry.pack(pady=10)

        self.root.mainloop()

    def reload_note(self):
        if not self.words_to_add:
            print("Wszystkie słówka dodane :)")
            self.root.destroy()
            return None
        self.current_word = self.words_to_add.pop(0)
        self.set_word()
        self.set_words_left()
        self.create_tree()
        self.image_val.set(0)
        self.error_val.set(0)
        self.gemini_diff_val.set(0)
        self.to_edit_val.set(0)
        self.sentences = []

    def load_words(self, path):
        with open(path, "r") as f:
            for line in f:
                self.words_to_add.append(line.strip())

    def diky_translations_harness(self, note: str):

        # Turned out to be easier way hehe
        meanings = self.diki_api.translation(note)
        if not meanings:
            print("ERROR - no translation")
        return meanings

    def add_slashes(self, meanings):
        """Adds slashes to meanings"""
        for array in meanings:
            array.append("SLASH")
        return meanings

    # --- FUNKCJA: tworzenie drzewa ---
    def create_tree(self):
        meanings = self.add_slashes(self.diky_translations_harness(self.current_word))
        if self.tree_frame is not None:
            self.tree_frame.destroy()

        self.tree_frame = ttk.Frame(self.frame_right)
        self.tree_frame.pack(fill="both", expand=True)

        self.translation_vars = []

        for row_idx, row in enumerate(meanings):
            row_frame = ttk.Frame(self.tree_frame)
            row_frame.pack(fill="x", pady=5)

            row_vars = []
            for translation in row:  # teraz row to lista tłumaczeń
                var = tk.IntVar(value=0)
                chk = ttk.Checkbutton(row_frame, text=translation, variable=var)
                chk.pack(side="left", padx=5)
                row_vars.append((translation, var))
            self.translation_vars.append(row_vars)

    # --- FUNKCJA: zmiana słowa ---
    def set_word(self):
        self.lbl_word.config(text=self.current_word)

    def set_words_left(self):
        self.lbl_words_left.config(text=f"{len(self.words_to_add)} - to add")

    def fetch_selected_translations(self):
        """
        Fetches selected by user translations and returns list of translations woven with 'SLASH'
        """
        selected = []
        for row in self.translation_vars:
            row_selected = [t for t, var in row if var.get() == 1]
            if row_selected:
                selected.append(row_selected)

        return [word for l in selected for word in l]

    def _on_add(self):

        back_html = parse_translations_to_html(self.fetch_selected_translations())
        tags = []
        if self.image_val.get() == 1:
            tags.append("IMAGE")
        if self.error_val.get() == 1:
            tags.append("ERROR")
        if self.gemini_diff_val.get() == 1:
            tags.append("GEMINI_DIFF")
        if self.to_edit_val.get() == 1:
            tags.append("TO_EDIT")

        audio_result = self.my_diki_api.diki_audio_harness(self.current_word)
        if not audio_result:
            print("ERROR - Audio ", self.current_word)
            audio_string = ""
            tags.append("noAudio")
        else:
            audio_string = f"[sound:{self.current_word}.mp3]"

        sentences = self.sentences_entry.get("1.0", "end-1c")
        if sentences:
            sentences = split_sentences(sentences)
            self.sentences.extend(sentences)

        sentences_html = None
        if self.sentences:
            sentences_html = sentences_html_generator(self.sentences)

        new_note_id = self.anki_api.add_flashcard(
            english_word=self.current_word,
            pl_translation=back_html,
            audio_en=audio_string,
            deck=self.deck,
            tags=tags,
            sentences=sentences_html,
        )

        if new_note_id == None:
            print("ERROR - Nie dodano anki")
        else:
            print("✅ Dodano: ", self.current_word)
            if not self.notes_db.add_word(new_note_id, self.current_word):
                print("ERROR - Redundand in DB")

        self.reload_note()

    def _on_description_request(self):
        self.gemini_bot.get_word_translation(self.current_word)

    def _on_sentences_request(self):
        current_translations = self.fetch_selected_translations()
        self.gemini_bot.get_word_sentences(self.current_word, current_translations)

    def _on_def_and_vis_request(self):
        vis = self.appConsole.on_def_and_vis_request(self.current_word)
        if vis:
            self.sentences.extend(vis)


def split_sentences(sentences_string):
    sentences = [s.strip() for s in sentences_string.split("$") if s.strip()]
    return sentences


def sentences_html_generator(sentences):
    return "\n<br><br>\n".join(sentences)


def parse_translations_to_html(meanings):

    if not meanings:
        return ""

    final_string = meanings.pop(0)
    while meanings:

        word = meanings.pop(0)
        if word != "SLASH":
            final_string += ", " + word
        else:
            if not meanings:
                print("ERROR - slash nie może być ostatni")
                return final_string
            final_string += "<br>\n" + meanings.pop(0)

    return final_string


class FlashcardAppConsole:
    def __init__(self):
        self.merriam_dict = MerriamWebsterDictApi()
        self.console = Console()

    def on_def_and_vis_request(self, word, data=None):
        if data is None:
            data = self.merriam_dict.get_definitions_with_sentences(word)

        if not data:
            print(f"\033[91mNo definitions found (word unknown)\033[0m")
            return

        elif isinstance(data[0], tuple):
            vis_count = 1
            vis_map = {}
            prompt = "Choose sentences (separated  by comma): "
            for word, definition, vis in data:
                self.console.print(f"\n _____ [bold blue]{word}[/bold blue] _____ ")
                self.console.print(f"[italic]{definition}[/italic]")
                if vis:
                    self.console.print("[yellow]Przykłady:[/yellow]")
                    for sentence in vis:
                        self.console.print(f"  {vis_count}. {sentence}", style="dim")
                        vis_map[vis_count] = sentence
                        vis_count += 1

            choice = self.console.input(prompt)

            chosen = []
            for num in choice.split(","):
                num = num.strip()
                if num.isdigit() and int(num) in vis_map:
                    chosen.append(vis_map[int(num)])

            if chosen:
                print("Accepted sentences:")
                for sentence in chosen:
                    self.console.print(f" - {sentence}", style="dim")
            else:
                print("No sentences typed")

            return chosen

        elif isinstance(data[0], str):
            self.console.print(
                "[red]No exact translation found, words closest found:[/red]",
                style="dim",
            )
            for i, word in enumerate(data):
                print(f"{i + 1}. {word}")
            prompt = "Choose new definition by number (or 0 to skip): "

            try:
                choice = int(self.console.input(prompt))
            except ValueError:
                print("That's not a valid integer!")
                return

            if choice == 0:
                return
            if 1 <= choice <= len(data):
                selected_word = data[choice - 1]
                data = self.merriam_dict.get_definitions_with_sentences(selected_word)
                self.on_def_and_vis_request(data)
                return
