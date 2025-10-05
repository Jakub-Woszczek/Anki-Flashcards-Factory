import requests
from bs4 import BeautifulSoup
from googlesearch import search
import os

# from notesModifier import NotesImprovement


class AnkiConnect:
    def __init__(self):
        self.test_card = 1755110613536
        # self.notes_improvement = NotesImprovement()
        self.MISSPELL_LABEL = "MISSPELL"
        self.images_folder_path = (
            r"C:\Users\icefr\AppData\Roaming\Anki2\Użytkownik 1\collection.media"
        )

    def invoke(self, action, **params):
        """Wyślij żądanie do AnkiConnect i zwróć wynik."""
        try:
            response = requests.post(
                "http://127.0.0.1:8765",
                json={"action": action, "version": 6, "params": params},
            )
            response.raise_for_status()  # Sprawdzenie, czy nie ma błędów HTTP
            return response.json()["result"]
        except requests.exceptions.RequestException as e:
            print(f"Błąd połączenia z AnkiConnect: {e}")
            return None

    def finding_cards_ids(self, deck_name=""):

        if deck_name:
            deck_name = "English::" + deck_name
        else:
            deck_name = "English"

        note_ids = self.invoke("findNotes", query=f"deck:{deck_name}")
        return note_ids

    def harness_cards_content(self, notes_ids):
        """
        Collets data about notes
        :param notes_ids: Array of notes ids
        :return: List of dictionaries aout each note
        """
        notes_list = self.invoke("notesInfo", notes=notes_ids)
        if notes_list:
            return notes_list
        return None

    def clean_html(self, text):
        raw_text = BeautifulSoup(text, "html.parser").get_text()
        normalized_text = raw_text.replace("\xa0", " ")
        normalized_text = " ".join(normalized_text.split())
        return normalized_text

    def spellcheck_deck(self, deck_name):
        print(f"Sprawdzam talie: {deck_name}")

        note_ids = self.finding_cards_ids(deck_name)
        notes_list = self.harness_cards_content(note_ids)

        if not notes_list:
            print(f"Deck {deck_name} has no cards")
            return None

        for note_data in notes_list:
            front_note = self.clean_html(note_data["fields"]["Przód"]["value"])
            back_note = self.clean_html(note_data["fields"]["Tył"]["value"])
            note_id = note_data["noteId"]
            print(f"Checking {note_id}")
            misspells_front = self.notes_improvement.spellcheck_pl(front_note)
            misspells_front_strig = ", ".join(misspells_front)
            if misspells_front:
                self.add_tag_to_note(note_id, self.MISSPELL_LABEL)
                self.modding_card(
                    note_id, front_note + "\n<br>" + misspells_front_strig, back_note
                )
                print(f"Front: {front_note}")
                print(f"Misspells: {misspells_front}")

            misspells_back = self.notes_improvement.spellcheck_en(back_note)
            misspells_back_strig = ", ".join(misspells_back)
            if misspells_back:
                self.add_tag_to_note(note_id, self.MISSPELL_LABEL)
                self.modding_card(
                    note_id, front_note, back_note + "\n<br>" + misspells_back_strig
                )
                print(f"Back: {back_note}")
                print(f"Misspells: {misspells_back}")

            print("")

    def finding_decks(self):
        # Pobierz wszystkie talie
        all_decks = self.invoke("deckNames")
        if all_decks:
            for deck in all_decks:
                print(deck)

    def subdecks(self, parent_deck):
        all_decks = self.finding_decks()
        subdecks_list = [d for d in all_decks if d.startswith(parent_deck + "::")]
        print(f"Subtalie talii {parent_deck}:")
        for d in subdecks_list:
            print("-", d)
        return subdecks_list

    def update_note_fields(self, note_id, fields: dict):
        """
        Zmodyfikuj tylko wybrane pola w notatce.
        :param note_id: int – ID notatki
        :param fields: dict – np. {"Przód": "Nowa treść"}
        """
        return self.invoke("updateNoteFields", note={"id": note_id, "fields": fields})

    def add_tag_to_note(self, note_id, tag):
        self.invoke("addTags", notes=[note_id], tags=tag)

    def get_image(self, note_id):
        """Zwróć nazwę pierwszego obrazka w danej fiszce."""

        # 2. Pobierz info o notatce
        notes = self.invoke("notesInfo", notes=[note_id])
        if not notes:
            print(f"Nie znaleziono notatki {note_id}")
            return None
        note = notes[0]

        card_html = note["fields"]["Tył"]["value"]

        soup = BeautifulSoup(card_html, "html.parser")
        img_tag = soup.find("img")

        if img_tag and "src" in img_tag.attrs:
            return img_tag["src"]  # np. "paste-5add636b6....jpg"
        else:
            # print(f"Brak obrazka w fiszce {note_id}")
            return None

    def get_text(self, note_id):
        notes = self.invoke("notesInfo", notes=[note_id])
        if not notes:
            print(f"Nie znaleziono notatki {note_id}")
            return None
        note = notes[0]

        card_html = note["fields"]["en_word"]["value"]

        soup = BeautifulSoup(card_html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        return text

    def get_content(self, note_id):
        notes = self.invoke("notesInfo", notes=[note_id])
        if not notes:
            print(f"Nie znaleziono notatki {note_id}")
            return None
        note = notes[0]

        return note["fields"]["pl_translation"]["value"]

    def add_flashcard(
        self, english_word, pl_translation, audio_en, deck=None, tags=None
    ):
        if deck == None:
            print("Nie podano talii")
            return

        assert type(english_word) == str
        assert type(pl_translation) == str
        assert type(deck) == str

        tags = tags or []
        assert isinstance(tags, list)

        note = {
            "deckName": deck,
            "modelName": "Basic [reverse+audio]",
            "fields": {
                "en_word": english_word,
                "pl_translation": pl_translation,
                "audio_en": audio_en,
            },
            "tags": tags or [],
            "options": {"allowDuplicate": False},
        }
        return self.invoke("addNote", note=note)

    def move_note_to_deck(self, note_id, new_deck):
        """
        Przenieś wszystkie karty z danej notatki do innej talii.
        :param note_id: int – ID notatki
        :param new_deck: str – docelowa talia
        """
        try:
            # Najpierw pobierz powiązane karty z notatki
            cards = self.invoke("findCards", query=f"nid:{note_id}")
            if not cards:
                print(f"❌ Brak kart dla notatki {note_id}")
                return None

            # Teraz przenieś karty do innej talii
            result = self.invoke("changeDeck", cards=cards, deck=new_deck)
            print(f"✅ Transfer complete")
            return result
        except Exception as e:
            print(f"transfer ERROR {note_id}: {e}")
            return None

    def get_note_tags(self, note_id: int):
        """
        Zwraca listę etykiet (tags) dla notatki o podanym ID.
        """
        result = self.invoke("notesInfo", notes=[note_id])
        if result is None:
            return None

        if not result:
            return []

        return result[0].get("tags", [])
