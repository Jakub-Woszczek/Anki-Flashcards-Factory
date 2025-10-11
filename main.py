import argparse
from flashcardApp import FlashcardApp
from dotenv import load_dotenv

from notesModifier import CasualNotesImprovement

load_dotenv()
parser = argparse.ArgumentParser()
parser.add_argument("-all", "--app", action="store_true", help="Runs flashcard app")
parser.add_argument("-modCasual","--mod", action="store_true", help="Runs casual modifications to flashcards")
args = parser.parse_args()

if args.app:
    path = r"other/flashcard_app_test_words.txt"
    test_deck = "English::toSort"
    app = FlashcardApp(path, test_deck)

if args.mod:
    notesMod = CasualNotesImprovement()
    notesMod.addSentencesToAlreadyCreated()
