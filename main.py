from allNotesDb import NotesDatabase
from ankiConnect import AnkiConnect
from notesModifier import NotesImprovement, casualNotesImprovement
from preparedNotesAdder import FlashcardApp
from RawNotesEditor import RawNotesEditor
if __name__ == "__main__":
    # app = FlashcardApp(r"prepared_notes/to_add_14.txt","English::D1")
    notes_improvement = casualNotesImprovement()
    # anki = AnkiConnect()
    # raw_notes_editor = RawNotesEditor()
    
    # raw_notes_editor.check_redundancy()
    # notes_improvement.add_deck_to_db("D1")
    # notes_improvement.check_audio()
    # for i in range(1,10):
    # notes_improvement.add_audio(f"C8[Obrazkowe]")
    notes_improvement.check_nbsp()
    pass