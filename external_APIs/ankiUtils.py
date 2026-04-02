from ankiConnect import AnkiConnect


class AnkiUtils:
    def __init__(self):
        self.anki_connect = AnkiConnect()

    def finding_cards_ids(self, deck_name=""):
        if deck_name:
            deck_name = "English::" + deck_name
        else:
            deck_name = "English"

        note_ids = self.anki_connect.invoke("findNotes", query=f"deck:{deck_name}")
        return note_ids

    def finding_decks(self):
        all_decks = self.anki_connect.invoke("deckNames")
        if all_decks:
            for deck in all_decks:
                print(deck)

    def get_note_tags(self, note_id: int):
        """
        Zwraca listę etykiet (tags) dla notatki o podanym ID.
        """
        result = self.anki_connect.invoke("notesInfo", notes=[note_id])
        if result is None:
            return None

        if not result:
            return []

        return result[0].get("tags", [])
