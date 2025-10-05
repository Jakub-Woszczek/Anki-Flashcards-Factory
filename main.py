from allNotesDb import NotesDatabase
from ankiConnect import AnkiConnect
from notesModifier import NotesImprovement, casualNotesImprovement
from preparedNotesAdder import FlashcardApp
from RawNotesEditor import RawNotesEditor
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    
    # app = FlashcardApp(r"prepared_notes/to_add_14.txt","English::D1")
    notes_improvement = casualNotesImprovement()
    notes_improvement.check_nbsp()
    pass