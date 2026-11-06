import os
from base64 import b64encode
from collections import Counter

import requests


REQUEST_TIMEOUT_SECONDS = 15


class AnkiConnect:
    def __init__(self):
        self.test_card = 1755110613536
        # self.notes_improvement = NotesImprovement()
        self.MISSPELL_LABEL = "MISSPELL"
        self.images_folder_path = os.getenv("ANKI_MEDIA_FOLDER_PATH")
        self.anki_URL = os.getenv("ANKI_URL", "http://127.0.0.1:8765")
        self.anki_base_deck_path = os.getenv("ANKI_BASE_DECK_PATH")
        self.last_error = None

    def invoke(self, action, **params):
        """Wyślij żądanie do AnkiConnect i zwróć wynik."""
        self.last_error = None
        try:
            response = requests.post(
                self.anki_URL,
                json={"action": action, "version": 6, "params": params},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()  # Sprawdzenie, czy nie ma błędów HTTP

            data = response.json()

            if data.get("error") is not None:
                self.last_error = str(data["error"])
                print(f"AnkiConnect error [{action}]: {data['error']}")
                print(f"params: {params}")
                return None
            return data.get("result")
        except requests.exceptions.RequestException as e:
            if isinstance(e, requests.exceptions.ConnectionError):
                self.last_error = (
                    f"Anki is not reachable at {self.anki_URL}. "
                    "Open Anki with the AnkiConnect add-on enabled, then refresh."
                )
            else:
                self.last_error = f"AnkiConnect request failed: {e}"
            return None

    def is_available(self):
        return self.invoke("version") is not None

    def sync(self) -> bool:
        """Synchronize the active Anki profile with AnkiWeb."""
        self.invoke("sync")
        return self.last_error is None

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
        return self.invoke("addTags", notes=[note_id], tags=tag)

    def remove_tag_from_note(self, note_id, tag):
        return self.invoke("removeTags", notes=[note_id], tags=tag)

    def add_note(self, deck, model, fields: dict, tags=None):
        if not deck or not model:
            self.last_error = "A deck and note type are required"
            return None
        return self.invoke(
            "addNote",
            note={
                "deckName": deck,
                "modelName": model,
                "fields": fields,
                "tags": tags or [],
                "options": {"allowDuplicate": False},
            },
        )

    def suspend_note_cards(self, note_id: int):
        card_ids = self.invoke("findCards", query=f"nid:{note_id}")
        if self.last_error:
            return None
        if not card_ids:
            self.last_error = f"No cards found for note {note_id}"
            return None
        return self.invoke("suspend", cards=card_ids)

    def delete_note(self, note_id: int):
        return self.invoke("deleteNotes", notes=[note_id])

    def store_media_file(self, filename: str, content: bytes):
        """Store audio in the media folder of Anki's active profile."""
        return self.invoke("storeMediaFile", filename=filename, data=b64encode(content).decode("ascii"))

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

        return self.add_note(
            deck,
            "Basic [reverse+audio]",
            {
                "en_word": english_word,
                "pl_translation": pl_translation,
                "audio_en": audio_en,
            },
            tags,
        )

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
        if not self.anki_base_deck_path:
            return []
        all_decks = self.invoke("deckNames") or []
        deck_names = [
            d
            for d in all_decks
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

    def get_note(self, note_id: int):
        notes = self.invoke("notesInfo", notes=[note_id])
        if not notes:
            return None
        note = notes[0]
        return note if note else None

    def get_note_cards(self, note_id: int):
        card_ids = self.invoke("findCards", query=f"nid:{note_id}") or []
        return self.cards_info(card_ids)

    def cards_info(self, card_ids):
        if not card_ids:
            return []
        cards = []
        for start in range(0, len(card_ids), 500):
            result = self.invoke("cardsInfo", cards=card_ids[start : start + 500]) or []
            cards.extend(card for card in result if card)
        return cards

    def notes_info(self, note_ids):
        if not note_ids:
            return []
        notes = []
        for start in range(0, len(note_ids), 500):
            result = self.invoke("notesInfo", notes=note_ids[start : start + 500]) or []
            notes.extend(note for note in result if note)
        return notes

    def find_notes_by_field(self, field_name: str, value: str):
        """Return candidate notes for a field query; callers verify exact values."""
        escaped_value = value.replace('"', '\\"')
        return self.invoke("findNotes", query=f'{field_name}:"{escaped_value}"') or []

    def deck_names(self):
        return self.invoke("deckNames") or []

    def model_names(self):
        return self.invoke("modelNames") or []

    def model_schema(self, model_name: str):
        fields = self.invoke("modelFieldNames", modelName=model_name)
        if fields is None:
            return None
        templates = self.invoke("modelTemplates", modelName=model_name) or {}
        styling = self.invoke("modelStyling", modelName=model_name) or {}
        return {"name": model_name, "fields": fields, "templates": templates, "styling": styling}

    def deck_models(self, deck_name: str):
        card_ids = self.invoke("findCards", query=f'deck:"{deck_name}"') or []
        return sorted({card.get("modelName") for card in self.cards_info(card_ids) if card.get("modelName")})

    def deck_model_counts(self, deck_name: str):
        card_ids = self.invoke("findCards", query=f'deck:"{deck_name}"') or []
        counts = Counter(
            card.get("modelName")
            for card in self.cards_info(card_ids)
            if card.get("modelName")
        )
        return [
            {"name": model_name, "count": count}
            for model_name, count in sorted(counts.items())
        ]

    def change_note_deck(self, note_id: int, deck_name: str):
        card_ids = self.invoke("findCards", query=f"nid:{note_id}") or []
        if not card_ids:
            self.last_error = f"No cards found for note {note_id}"
            return None
        return self.invoke("changeDeck", cards=card_ids, deck=deck_name)

    def set_card_flag(self, card_id: int, flag: int):
        """Use AnkiConnect's undocumented card field setter when available."""
        if flag < 0 or flag > 7:
            self.last_error = "Flag must be between 0 and 7"
            return None
        result = self.invoke(
            "setSpecificValueOfCard",
            card=card_id,
            keys=["flags"],
            newValues=[flag],
        )
        if self.last_error:
            return None
        return result

    def set_note_cards_flag(self, note_id: int, flag: int):
        card_ids = self.invoke("findCards", query=f"nid:{note_id}")
        if self.last_error:
            return None
        if not card_ids:
            self.last_error = f"No cards found for note {note_id}"
            return None
        for card_id in card_ids:
            self.set_card_flag(card_id, flag)
            if self.last_error:
                return None
