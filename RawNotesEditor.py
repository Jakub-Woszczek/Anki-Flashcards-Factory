import requests
from bs4 import BeautifulSoup
from allNotesDb import NotesDatabase
from external_APIs.ankiConnect import AnkiConnect
import os


class RawNotesEditor:
    def __init__(self):
        self.anki = AnkiConnect()
        self.dir = "raw_notes"
        self.diki_url = "https://www.diki.pl/slownik-angielskiego?q="
        self.db = NotesDatabase()

    def strip_from_empty_lines(self, path):
        # USELESS
        file_name = os.path.basename(path)
        folder = os.path.dirname(path)
        name, ext = os.path.splitext(file_name)
        new_name = name + "_v1" + ext
        new_path = os.path.join(folder, new_name)

        with open(new_path, "w") as f_new:
            with open(path, "r") as f:
                for line in f:
                    if line.strip() != "":
                        f_new.write(line)

    def diki_possible_spellings(self, soup):
        """Returns list of possible spellings or phrasal verbs"""

        phrases = []
        suggestions = soup.select("div.dictionarySuggestions a")
        for a in suggestions:
            text = a.get_text()
            text = text.replace("\xa0", " ")
            text = " ".join(text.split())
            phrases.append(text)
        return phrases

    def prepare_raw_notes(self, file):
        path = os.path.join(self.dir, file)
        name, ext = os.path.splitext(file)
        name_new = "input_correct" + ext
        path_correct = os.path.join(self.dir, name_new)
        errors = "errors.txt"
        errors_path = os.path.join(self.dir, errors)

        with open(path, "r") as f, open(path_correct, "w") as f_correct, open(
            errors_path, "w"
        ) as f_errors:

            for line in f:
                line = line.strip().lower()
                response = requests.get(self.diki_url + line)
                html = response.text
                soup = BeautifulSoup(html, "html.parser")
                possible_spellings = self.diki_possible_spellings(soup)
                print(f"CHECK {line}")
                if line in possible_spellings:
                    print(f"Słowo: {line} ✔")
                    f_correct.write(line + "\n")
                else:
                    if possible_spellings:
                        print(f"Możliwe poprawne wersje [{line}]:")
                        for i, spelling in enumerate(possible_spellings, start=1):
                            print(f"{i}. {spelling}")

                        try:
                            choice = int(
                                input("Wybierz numer poprawnej wersji (0 = pomiń): ")
                            )
                            if 1 <= choice <= len(possible_spellings):
                                selected = possible_spellings[choice - 1]
                                f_correct.write(selected + "\n")
                                print(f"→ Zapisano: {selected}")
                            else:
                                print("→ Pominięto.")
                                f_errors.write(line + "\n")
                        except ValueError:
                            print("→ Niepoprawny wybór")
                            f_errors.write(line + "\n")
                    else:
                        print("→ Słówko nie istnieje w diki ani nie ma podobnych")
                        f_errors.write(line + "\n")

    def check_redundancy(self):
        """Checks inner redundancy within file and DB"""
        # TODO why the same txt file??
        notes_path = r"prepared_notes/diki_prepared.txt"
        clean_notes_path = r"prepared_notes/diki_prepared.txt"
        inner_redundant = []

        with open(notes_path, "r") as f_notes, open(
            clean_notes_path, "w"
        ) as f_clean_notes:

            for line in f_notes:
                line = line.strip()
                if line not in inner_redundant:
                    if not self.db.is_in_db(line):
                        f_clean_notes.write(line + "\n")
                        inner_redundant.append(line)
                    else:
                        print("DB r: ", line)
                else:
                    print("INNER r: ", line)
