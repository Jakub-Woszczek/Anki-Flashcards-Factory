import requests


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
        # TODO funkcja do usunięcia/przeniesienia do innej klasy
        if deck_name:
            deck_name = "English::" + deck_name
        else:
            deck_name = "English"

        note_ids = self.invoke("findNotes", query=f"deck:{deck_name}")
        return note_ids

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

    def finding_decks(self):
        # TODO funkcja do usunięcia/przeniesienia do innej klasy, opis invoke actions jest tutaj: https://github.com/amikey/anki-connect
        all_decks = self.invoke("deckNames")
        if all_decks:
            for deck in all_decks:
                print(deck)

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

    def get_note_tags(self, note_id: int):
        # TODO funkcja do usunięcia/przeniesienia do innej klasy
        """
        Zwraca listę etykiet (tags) dla notatki o podanym ID.
        """
        result = self.invoke("notesInfo", notes=[note_id])
        if result is None:
            return None

        if not result:
            return []

        return result[0].get("tags", [])
