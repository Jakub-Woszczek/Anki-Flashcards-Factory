from diki_translate import Diki
import tkinter as tk
from tkinter import ttk
from ankiConnect import AnkiConnect
from dikiApi import DikiApi
from geminiAPI import GeminBot
from allNotesDb import NotesDatabase


class FlashcardApp:
    def __init__(self, path, deck):
        self.translation_vars = []
        self.tree_frame = None
        self.gemini_bot = GeminBot()
        self.words_to_add = []
        self.diki_api = Diki("english")
        self.my_diki_api = DikiApi()
        self.anki_api = AnkiConnect()
        self.notes_db = NotesDatabase()
        self.deck = deck

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

    def _on_add(self):
        selected = []
        for row in self.translation_vars:
            row_selected = [t for t, var in row if var.get() == 1]
            if row_selected:
                selected.append(row_selected)

        back_html = parse_translations_to_html(selected)
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

        new_note_id = self.anki_api.add_flashcard(
            self.current_word, back_html, audio_string, self.deck, tags
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


def parse_translations_to_html(meanings):
    """Accepts nested list of translations with slashes"""
    meanings_flatten = [word for nested_list in meanings for word in nested_list]
    if not meanings_flatten:
        return ""

    final_string = meanings_flatten.pop(0)
    while meanings_flatten:

        word = meanings_flatten.pop(0)
        if word != "SLASH":
            final_string += ", " + word
        else:
            if not meanings_flatten:
                print("ERROR - slash nie może być ostatni")
                return final_string
            final_string += "<br>\n" + meanings_flatten.pop(0)

    return final_string
