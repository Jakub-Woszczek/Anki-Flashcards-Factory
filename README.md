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
# Opcjonalnie: katalog eksportu dla starszych narzedzi terminalowych.
# Aplikacja przegladarkowa wysyla audio do aktywnego profilu przez AnkiConnect.
ANKI_MEDIA_FOLDER_PATH="/path/to/Anki2/User 1/collection.media"

# Domyslnie: http://127.0.0.1:8765
ANKI_URL=http://127.0.0.1:8765

# Opcjonalnie, dla pomocy Gemini
GEMINI_API_KEY=

# Opcjonalnie, domyslnie: data/anki_flashcards_factory.sqlite3
ANKI_FACTORY_DB_PATH=data/anki_flashcards_factory.sqlite3

# Opcjonalnie, wspolny cache HTML i MP3
DIKI_CACHE_DIR=data/diki_cache

# Opcjonalnie, folder list .txt (rowniez podfoldery)
DIKI_WORDS_DIR=words_to_add

# Odstep po KAZDYM zadaniu: 20 sekund +/- losowe 5 sekund
DIKI_REQUEST_JITTER_SECONDS=5
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

## Diki offline: HTML i MP3

Aplikacja i narzedzia terminalowe korzystaja ze wspolnego modulu zasobow:
najpierw odczyt z dysku, a jesli zasobu brakuje — pobranie z Diki i zapis w cache.
Surowy HTML jest parsowany lokalnie, wiec zmiana parsera nie wymaga ponownego
pobierania stron. Cache nie wygasa automatycznie. Nie jest powiazany z profilem
Anki ani kolejkami sesji.

Panel **Offline downloads** na stronie glownej pokazuje dla kazdej listy:
liczbe pobranych HTML i MP3, procent gotowych slow (dokladne znaczenie + MP3),
brak dokladnego dopasowania, brak nagrania, bledy przejsciowe oraz ostatnia partie.
Odswieza sie co minute i nie wykonuje zadan do Diki ani Anki. Procenty liczone sa
po unikalnych slowach; duplikaty i wspolne slowa w roznych listach pobierane sa raz.

### Reczne pobieranie

Po aktywowaniu tego samego srodowiska Python co dla aplikacji:

```bash
# Glowna lista ma pierwszenstwo, potem pozostale .txt w words_to_add/.
python -m tools.diki_prefetch --batch-size 25 --max-runtime 600

# Wieksza partia, np. przed wyjazdem (odstepy nadal obowiazuja).
python -m tools.diki_prefetch --batch-size 200 --max-runtime 7200

# Tylko lokalny raport JSON, bez pobierania.
python -m tools.diki_prefetch --report

# Wybrany folder, np. jedna ksiazka.
python -m tools.diki_prefetch --words-dir words_to_add/books
```

Dodanie nowego pliku `.txt` do folderu list wystarcza, aby nastepna partia go
uwzglednila. Format: jedno slowo lub fraza w linii, UTF-8. Puste linie sa
pomijane, wielkosc liter i nadmiarowe spacje nie tworza nowych zasobow. Listy nie
sa modyfikowane przez downloader. Wgranie pliku tylko przez przegladarke nie
kopiuje go automatycznie do tego folderu.

Kazde zadanie HTTP (HTML, MP3, kolejne warianty nagrania) czeka 15–25 sekund
od zakonczenia poprzedniego. Kolejny odstep jest losowany niezaleznie. Blokada i
termin nastepnego zadania sa wspolne dla aplikacji i procesu tla, rowniez po
restarcie. Trafienia w cache nie czekaja. Limit 600 sekund obejmuje te odstepy,
wiec partia moze zakonczyc sie przed 25 slowami. Nastepna kontynuuje brakujace
zasoby i zapamietany wariant MP3, zamiast zaczynac od nowa.

HTTP 403/429 lub rozpoznana strona anti-bot wstrzymuja pobieranie na co najmniej
6 godzin; dluzszy `Retry-After` jest respektowany. Bledy polaczenia zatrzymuja
partie na 5 minut. Pojedynczy `ReadTimeout` lub blad serwera 5xx odklada tylko
dane slowo i pozwala probowac kolejne. Trzy takie bledy z rzedu zatrzymuja partie
na 5 minut, nadal z odstepami 15–25 sekund miedzy zadaniami. Inne bledy HTTP lub
nieprawidlowe odpowiedzi wstrzymuja pobieranie na co najmniej 30 minut.
Ponawianie blednego zasobu ma rosnacy odstep: 30 minut do 24 godzin.
Takie odpowiedzi nie zastepuja dobrego cache. Strony 404 z sugestiami sa
zapisywane, ale nie licza sie jako dokladne dopasowanie. Nie pobieramy dla nich
zgadywanych MP3. Potwierdzony brak nagrania nie jest ponawiany co partie.

Raport zachowuje rodzaj bledu (np. `ReadTimeout` lub `HTTP 524`). HTTP 524 oznacza,
ze Cloudflare nie doczekal sie odpowiedzi serwera Diki; nie jest sam w sobie
dowodem blokady anti-bot. Zwykle strony slownika zawieraja skrypt Cloudflare —
jego obecnosc obok poprawnych definicji nie powoduje odrzucenia HTML.

`--refresh` jawnie odswieza zasoby, w tym potwierdzone braki, w granicach podanej
partii. Nadal respektuje wspolne odstepy i cooldown. Przy odswiezaniu wybranych
list uzyj `--words-dir`. Normalny harmonogram powinien dzialac bez `--refresh`.

### Harmonogram macOS (launchd)

Generator zapisuje plist z absolutna sciezka do **aktualnie uzywanego Pythona**
i projektu. Uruchom go po aktywowaniu wlasciwego virtualenv:

```bash
python -m tools.diki_launchd
mkdir -p "$HOME/Library/LaunchAgents"
cp data/com.anki-flashcards-factory.diki-prefetch.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.anki-flashcards-factory.diki-prefetch.plist"
```

Agent uruchamia partie przy zalogowaniu i co 30 minut, niezaleznie od aplikacji.
Nie budzi uspionego Maca. Nakladajace sie uruchomienia sa pomijane. Czyta `.env`
z katalogu projektu; `DIKI_CACHE_DIR` i `DIKI_WORDS_DIR` sa wiec wspolne z aplikacja.
Logi: `data/diki-prefetch.log` i `data/diki-prefetch-error.log`.

Zatrzymanie i usuniecie harmonogramu:

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.anki-flashcards-factory.diki-prefetch.plist"
rm "$HOME/Library/LaunchAgents/com.anki-flashcards-factory.diki-prefetch.plist"
```

Po przeniesieniu projektu lub zmianie virtualenv zatrzymaj agenta, wygeneruj
plik ponownie i zainstaluj go pod nowymi sciezkami.

### Praca bez internetu

Dla pobranych slow nie sa potrzebne zadania do Diki. Aby wymusic brak zadan
rowniez przy brakujacych zasobach, uruchom aplikacje tak:

```bash
DIKI_OFFLINE=1 python main.py --app
```

Brak HTML bedzie wtedy widoczny jako brak lokalnego zasobu, a nie blad pisowni.
Brak audio pozwala stworzyc fiszke tekstowa; aktualizacja nie usuwa istniejacego
nagrania. Lokalne Anki nadal musi dzialac do zapisu kart. Gemini i AnkiWeb sync
wymagaja internetu; blad synchronizacji nie cofa lokalnego zapisu.

Ustawienie `DIKI_OFFLINE=1` w `.env` wylacza takze pobieranie przez proces tla.

### Weryfikacja bez sieci

```bash
python -m unittest tests.test_diki_resources tests.test_dikiApi tests.test_diki_meanings tests.test_diki_regression tests.test_audio_sync tests.test_review_stateless tests.test_target_selection tests.test_sync_rate_limit tests.test_session_storage tests.test_queue_diff
```

Testy korzystaja z zapisanych stron i atrap HTTP/Anki. Dwa starsze testy live
Diki sa domyslnie pomijane (`RUN_LIVE_DIKI_TESTS=1` wlacza je jawnie).

## Dane lokalne

- `data/anki_flashcards_factory.sqlite3` - indeks notatek i sesje.
- `data/diki_cache/` - HTML, MP3 i osobna baza metadanych, odstepow i postepu pobierania.
- `words_to_add/words_to_add.txt` - opcjonalna lista slow do zaimportowania w kolejnosci linii.
- `raw_notes/` - pliki dla starszego, terminalowego preprocessingu.

Starszy indeks JSON ustawiony przez `DATABASE_PATH` jest jednokrotnie
importowany do SQLite przy pierwszym uruchomieniu.
