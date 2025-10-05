from spellchecker import SpellChecker
import requests
from bs4 import BeautifulSoup
import tkinter as tk
from PIL import Image, ImageTk
import os

from allNotesDb import NotesDatabase
from dikiApi import DikiApi
from ankiConnect import AnkiConnect


class NotesImprovement:
    def __init__(self):
        import re

        self.re = re
        self.polish_dic_path = "raw_notes/pl_dic.txt"
        self.abbreviations = ["np", "np.", "itp", "itp."]
        self.diki_api = DikiApi()

        self.spell_en = SpellChecker(language="en")
        self.spell_pl = SpellChecker(language=None)
        self.spell_pl.word_frequency.load_text_file(self.polish_dic_path)

        # Tinkter
        self.images_folder_path = (
            r"C:\Users\icefr\AppData\Roaming\Anki2\Użytkownik 1\collection.media"
        )
        self.anki = AnkiConnect()
        self.diki_api = DikiApi()
        self.first_load = True
        self.current_note_id = None
        self.current_front = None
        self.current_back = None
        pass

    def parse_raw_notes(self):
        path = "raw_notes/English__1#_IT 2.txt"

        with open(path, "r", encoding="utf-8") as file:
            for line in file:
                parsed_note = {"front": None, "back": None}
                match = self.re.match(r"([^\t]*)\t(.*)", line)
                if match:
                    parsed_note["front"] = match.group(1)
                    parsed_note["back"] = match.group(2)
                # print(line.strip())
                print(f"'<{parsed_note['front']}><{parsed_note['back']}>',")

    def split_words_en(self, note):
        """Split note into clean words."""
        elements = self.re.split(r"[\/,\(\)\s]", note)
        return [e.strip() for e in elements if e.strip()]

    def split_words_pl(self, note):
        # 1. usuń wszystko w nawiasach
        no_parens = self.re.sub(r"\([^)]*\)", "", note)

        # 2. rozdziel po przecinkach i slashach
        elements = self.re.split(r"[\/,]", no_parens)

        # 3. posprzątaj
        return [e.strip() for e in elements if e.strip()]

    def spellcheck_pl(self, text):
        """Check Polish spelling errors.
        HTTP request do dicky.pl and check whether it correctly written."""

        return [
            w for w in self.split_words_pl(text) if self.diki_api.word_request_diki(w)
        ]

    def spellcheck_en(self, text):
        """Check English spelling errors."""
        return [w for w in self.split_words_en(text) if w not in self.spell_en]

    def images_improvement(self, deck_name):
        # Finding cards ids and images names
        notes_ids = self.anki.finding_cards_ids(deck_name)
        notes_data = self.anki.harness_cards_content(notes_ids)
        print(notes_ids)

        def load_card(event=None):
            # Jeżeli to nie pierwsze załadowanie, zapisz odpowiedź
            if not self.first_load:
                tekst = entry.get()
                entry.delete(0, tk.END)

                if tekst != "" and self.current_note_id:
                    self.anki.modding_card(
                        self.current_note_id, self.current_front, tekst
                    )
                    print("Zapisano odpowiedź:", tekst)
            else:
                self.first_load = False

            # Jeśli nie ma już kart → kończymy
            if not notes_ids:
                print("Brak więcej fiszek.")
                return

            # Pobierz kolejną kartę
            note_id = notes_ids.pop(0)
            note_data = notes_data.pop(0)
            cards_left_label.config(text=f"Zostało fiszek: {len(notes_ids)}")

            front = note_data["fields"]["Przód"]["value"]
            back = note_data["fields"]["Tył"]["value"]

            # Zapamiętaj jako aktualną
            self.current_note_id = note_id
            self.current_front = front
            self.current_back = back

            # Załaduj obrazek
            image_name = self.anki.get_image(note_id)
            zaladuj_obrazek(image_name)

        # Funkcja ładowania obrazka
        def zaladuj_obrazek(image_name):
            if image_name == None:
                image = Image.open("raw_notes/none.png")
                photo = ImageTk.PhotoImage(image)
                label_obrazek.config(image=photo)
                label_obrazek.image = photo  # trzeba trzymać referencję
                return None

            sciezka = os.path.join(self.images_folder_path, image_name)

            if os.path.exists(sciezka):
                image = Image.open(sciezka)
                photo = ImageTk.PhotoImage(image)
                label_obrazek.config(image=photo)
                label_obrazek.image = photo  # trzeba trzymać referencję
            else:
                print("Nie znaleziono pliku:", sciezka)

        # Tworzymy okno
        root = tk.Tk()
        root.title("Fiszki z obrazkiem")

        # Label do wyświetlania obrazka (bez stałego rozmiaru)
        label_obrazek = tk.Label(root)
        label_obrazek.pack(pady=10)

        # Frame pod obrazkiem z buttonem i polem tekstowym
        frame = tk.Frame(root)
        frame.pack(pady=5)

        # Przycisk po lewej
        button = tk.Button(frame, text="Kliknij mnie", command=load_card)
        button.pack(side=tk.LEFT)

        # Pole tekstowe po prawej
        entry = tk.Entry(frame, width=30)
        entry.pack(side=tk.LEFT, padx=10)
        entry.bind("<Return>", load_card)  # Enter wywołuje funkcję

        cards_left_label = tk.Label(root, text=f"{len(notes_ids)}")
        cards_left_label.pack(pady=5)

        load_card()

        root.mainloop()

    def finding_cards_with_images(self, deck_name):

        notes_ids = self.anki.finding_cards_ids(deck_name)
        notes_data = self.anki.harness_cards_content(notes_ids)

        for note_id in notes_ids:
            image_name = self.anki.get_image(note_id)
            if image_name != None:
                self.anki.add_tag_to_note(note_id, "IMAGE")
                print(f"Dodano tag do {note_id}")


class casualNotesImprovement:
    def __init__(self):
        self.anki = AnkiConnect()
        self.diki_api = DikiApi()
        self.db = NotesDatabase()
        pass

    def add_deck_to_db(self, deck_name):
        notes_ids = self.anki.finding_cards_ids(deck_name)
        db_data = []
        for note_id in notes_ids:
            tags = self.anki.get_note_tags(note_id)
            if tags != None and "addDB" in tags:
                word = self.anki.get_content(note_id)
                if word == "" or word is None:
                    print(f"Error {note_id}")
                    continue
                else:
                    db_data.append((note_id, word))
                    print(word)

        self.db.add_words(db_data)

    def add_audio(self, deck_name):
        print(deck_name)
        notes_ids = self.anki.finding_cards_ids(deck_name)
        path = r"C:\Users\icefr\AppData\Roaming\Anki2\Użytkownik 1\collection.media"

        for note_id in notes_ids:
            en_word = self.anki.get_content(note_id)
            file_path = os.path.join(path, en_word + ".mp3")

            if os.path.exists(file_path):
                print("Ścieżka zajęta dla: ", en_word)
            else:
                if not self.diki_api.diki_audio_harness(en_word):
                    print("ERROR - audio fetch failed for: ", en_word)
                    self.anki.add_tag_to_note(note_id, "noAudio")
                else:
                    audio_string = f"[sound:{en_word}.mp3]"
                    self.anki.update_note_fields(note_id, {"audio_en": audio_string})

    def check_nbsp(self):
        notes_ids = self.anki.finding_cards_ids()

        for note_id in notes_ids:
            content = self.anki.get_content(note_id)
            if content == "":
                continue
            print(content)
            new_content = content.replace("&nbsp;", " ").strip()
            # print(new_content)
            if new_content == content:
                continue
            # self.anki.update_note_fields(note_id, {"pl_translation" : new_content})
