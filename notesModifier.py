import os
from allNotesDb import NotesDatabase
from dikiApi import DikiApi
from ankiConnect import AnkiConnect


class CasualNotesImprovement:
    def __init__(self):
        self.anki = AnkiConnect()
        self.diki_api = DikiApi()
        self.db = NotesDatabase()
        pass
