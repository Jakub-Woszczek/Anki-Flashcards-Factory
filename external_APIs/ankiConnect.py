import os
import requests


class AnkiConnect:
    def __init__(self):
        self.test_card = 1755110613536
        # self.notes_improvement = NotesImprovement()
        self.MISSPELL_LABEL = "MISSPELL"
        self.images_folder_path = os.getenv("ANKI_MEDIA_FOLDER_PATH")
        self.anki_URL = os.getenv("ANKI_URL")
        self.anki_base_deck_path = os.getenv("ANKI_BASE_DECK_PATH")

    def invoke(self, action, **params):
        """Wyślij żądanie do AnkiConnect i zwróć wynik."""
        try:
            response = requests.post(
                self.anki_URL,
                json={"action": action, "version": 6, "params": params},
            )
            response.raise_for_status()  # Sprawdzenie, czy nie ma błędów HTTP

            data = response.json()

            if data.get("error") is not None:
                print(f"AnkiConnect error: {data['error']}")
                return None
            return data.get("result")

        except requests.exceptions.RequestException as e:
            print(f"Błąd połączenia z AnkiConnect: {e}")
            return None

    def harness_cards_content(self, notes_ids):
        """
        Collects data about notes
        :param notes_ids: Array of notes ids
        :return: List of dictionaries about each note
        """
        notes_list = self.invoke("notesInfo", notes=notes_ids)
        if notes_list:
            return notes_list
        return None

    def update_note_fields(self, note_id, fields: dict):
        """
        Zmodyfikuj tylko wybrane pola w notatce.
        :param note_id: Int – ID notatki
        :param fields: dict – np. {"Przód": "Nowa treść"}
        """
        return self.invoke("updateNoteFields", note={"id": note_id, "fields": fields})

    def add_tag_to_note(self, note_id, tag):
        self.invoke("addTags", notes=[note_id], tags=tag)

    def add_flashcard(
        self, english_word, pl_translation, audio_en, deck=None, tags=None
    ):
        if deck == None:
            print("Nie podano talii")
            return None

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

    def move_note_to_deck(self, note_id: int, new_deck: str):
        """
        Przenieś wszystkie karty z danej notatki do innej talii.
        :param note_id: ID notatki
        :param new_deck: docelowa talia
        """
        try:
            cards = self.invoke("findCards", query=f"nid:{note_id}")
            if not cards:
                print(f"❌ Brak kart dla notatki {note_id}")
                return None

            result = self.invoke("changeDeck", cards=cards, deck=new_deck)
            print(f"✅ Transfer complete")
            return result
        except Exception as e:
            print(f"transfer ERROR {note_id}: {e}")
            return None

    def get_subdecks(self):
        """
        Returns list of subdecks of supreme deck (ANKI_BASE_DECK_PATH).
        """
        deck_names = [
            d
            for d in self.invoke("deckNames")
            if d.startswith(
                self.anki_base_deck_path + "::"
            )  # Checks if is subdeck of supreme deck
            and any(char.isdigit() for char in d)
            and "C2" not in d  # I have in my supreme deck some additional decks that I
        ]  # want to exclude, and they don't have digits in their names

        return deck_names

    def notes_ids_from_deck(self, deck_name):
        query = f"deck:{deck_name}"
        r = self.invoke("findNotes", query=query)
        if r is None:
            raise ValueError(f"Nie znaleziono notatek w talii {deck_name}")
        return r
