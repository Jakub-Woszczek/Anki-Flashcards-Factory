# Anki Flashcards Factory

Lokalna aplikacja do tworzenia i edycji fiszek angielsko-polskich w Anki.
Pobiera tlumaczenia i audio z Diki, zapisuje notatki przez AnkiConnect oraz
pozwala wznawiac przerwane sesje.

## Wymagania

- Python 3.11+
- Node.js 20+
- Anki z dodatkiem [AnkiConnect](https://ankiweb.net/shared/info/2055492159)

Gemini jest opcjonalny.

## Instalacja

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd frontend
npm install
npm run build
cd ..
```

## Konfiguracja

Utworz `.env` w katalogu projektu:

```env
# Lokalizacja collection.media dla profilu Anki
ANKI_MEDIA_FOLDER_PATH="/path/to/Anki2/User 1/collection.media"

# Domyslnie: http://127.0.0.1:8765
ANKI_URL=http://127.0.0.1:8765

# Opcjonalnie, dla pomocy Gemini
GEMINI_API_KEY=

# Opcjonalnie, domyslnie: data/anki_flashcards_factory.sqlite3
ANKI_FACTORY_DB_PATH=data/anki_flashcards_factory.sqlite3
```

## Uruchomienie

Uruchom Anki, a nastepnie:

```bash
python main.py --app
```

Aplikacja otworzy sie pod adresem `http://127.0.0.1:8000`.
Uzyj `--no-browser`, aby nie otwierac automatycznie przegladarki.

Podczas pracy frontendowej uruchom osobno:

```bash
cd frontend
npm run dev
```

Serwer Vite przekazuje zadania `/backend` do backendu na porcie `8000`.

## Workflow

1. Wklej liste slow lub utworz sesje z `words_to_add/words_to_add.txt`.
2. Wybierz talie, typ notatki i mapowanie pol Anki.
3. Dla kazdego slowa wybierz tlumaczenia z Diki, dodaj tagi i sprawdz podglad.
4. Utworz nowa notatke albo zaktualizuj istniejaca.

Sesje, kolejki i szkice sa zapisywane w lokalnej bazie SQLite, wiec mozna je
wznowic po zamknieciu aplikacji. Widok review pozwala przejsc przez notatki
wybrane tagiem lub flaga Anki.

Zmiany w Anki sa synchronizowane z AnkiWeb bezposrednio po pierwszej zmianie,
a kolejne synchronizacje sa ograniczone do jednej na 10 sekund. Przycisk
`Sync & stop` na stronie glownej wymusza synchronizacje oczekujacych zmian i
bezpiecznie zatrzymuje lokalny serwer. Pojedyncze Ctrl-C w terminalu rowniez
wykonuje oczekujaca synchronizacje podczas zamykania.

## Dane lokalne

- `data/anki_flashcards_factory.sqlite3` - indeks notatek i sesje.
- `words_to_add/words_to_add.txt` - opcjonalna lista slow do zaimportowania w kolejnosci linii.
- `raw_notes/` - pliki dla starszego, terminalowego preprocessingu.

Starszy indeks JSON ustawiony przez `DATABASE_PATH` jest jednokrotnie
importowany do SQLite przy pierwszym uruchomieniu.
