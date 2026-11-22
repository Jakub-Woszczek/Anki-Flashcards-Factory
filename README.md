# Anki Flashcards Factory

Lokalna aplikacja do tworzenia i edycji fiszek angielsko-polskich w Anki.
Pobiera tlumaczenia i audio z Diki, zapisuje notatki przez AnkiConnect oraz
pozwala wznawiac przerwane sesje.

Dokumentacja projektu: [Project handbook](docs/index.md).
Punkt wznowienia przegladu: [Walkthrough checkpoint](docs/review.md).
Luzne pomysly i przypomnienia: [Todo](docs/todo.md) — nie sa planem implementacji.
Zrealizowane zmiany: [Feature map](docs/features.md).

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

### Narzedzia developerskie i automatyczne sprawdzanie

Po aktywowaniu srodowiska projektu (istniejace `.ankiFac` albo `.venv` z instrukcji
instalacji):

```bash
python -m pip install -r requirements-dev.txt
python -m pre_commit install
npm --prefix frontend ci
python -m tools.check
```

`tools.check` uruchamia Ruff lint/format, Pyright, testy offline z blokada sieci
oraz TypeScript/build frontendu. Hooki sprawdzaja odpowiednie zmienione pliki przy
commitach; GitHub Actions wykonuje pelny zestaw. Hooki wymagaja aktywnego srodowiska.
Formatowanie/fixy sa jawne:

```bash
python -m ruff check --fix .
python -m ruff format .
```

Wspolne ustawienia `.vscode/` dotycza tylko tego repo: Ruff formatuje Python przy
zapisie, a Pylance korzysta z konfiguracji Pyright w `pyproject.toml`. W VS Code
wybierz interpreter tego samego srodowiska przez **Python: Select Interpreter**.
Zadanie **Quality: all checks** uruchamia pelna weryfikacje. Globalne ustawienia
VS Code nie sa zmieniane. Szczegoly: [Development and verification](docs/development.md).

### Ustawienia aplikacji

Utworz `.env` w katalogu projektu:

```env
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

# Bazowy odstep procesu tla; adaptacja moze go zwiekszyc po blokadzie.
DIKI_BACKGROUND_INTERVAL_SECONDS=20

# Losowy dodatek/odjecie od aktualnego odstepu procesu tla.
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

1. Na stronie glownej otworz glowny plik `words_to_add/words_to_add.txt` albo
   ksiazkowy plik `.txt` z `words_to_add/` (rowniez podfoldery).
2. Wybierz talie, typ notatki i mapowanie pol Anki.
3. Dla kazdego slowa wybierz tlumaczenia z Diki, dodaj tagi i sprawdz podglad.
4. Utworz nowa notatke, zaktualizuj istniejaca albo wybierz **Discard from queue**.

Angielskie haslo pochodzi z Diki, z zachowaniem wielkosci liter: `basel` →
`Basel`, `lead astray` → `lead somebody astray`. Dokladna pisownia ma
pierwszenstwo; `Polish` i `polish` maja oddzielne znaczenia. Niejednoznaczny
wynik wymaga wyboru podpowiedzi. Dotyczy to tez zapisu slow przez CLI.
Zasady: [Diki headwords and case](docs/decisions/0005-diki-headwords-and-case.md).

Plik jest kolejka: kolejnosc i pozostale slowa sa odczytywane bezposrednio z niego.
SQLite przechowuje ustawienia celu, szkic biezacego wpisu i historie operacji,
bez drugiej kopii listy slow. Dodawaj slowa przez CLI lub edytuj pliki tekstowe.
Usunieto wklejanie/upload list, tworzenie/nazywanie kolejek, edytor/diff kolejek
i ich usuwanie na stronie glownej. **Refresh** odczytuje aktualne pliki/liczniki;
**Reload source** w widoku slowa ponownie wczytuje zrodlo po zewnetrznej zmianie.
Dodane przez CLI slowa sa tez widoczne przy przechodzeniu do kolejnych wpisow.
Widok review pozwala przejsc przez notatki wybrane tagiem lub flaga Anki.

Zmiany w Anki sa synchronizowane z AnkiWeb bezposrednio po pierwszej zmianie,
a kolejne synchronizacje sa ograniczone do jednej na 10 sekund. Przycisk
`Sync & stop` na stronie glownej wymusza synchronizacje oczekujacych zmian i
bezpiecznie zatrzymuje lokalny serwer. Pojedyncze Ctrl-C w terminalu rowniez
wykonuje oczekujaca synchronizacje podczas zamykania.

## Usuwanie dodanych slow z listy

Po zapisie aplikacja odczytuje notatke przez AnkiConnect po zwroconym `noteId`
i porownuje typ, wyslane pola, wymagane/usuwane tagi oraz talie kart. Nowe notatki
trafiaja do wybranej talii; aktualizacja zachowuje dotychczasowa talie kazdej karty
istniejacej notatki i sprawdza ja przy odczycie kontrolnym oraz ponowieniu zapisu.
Po zgodnym odczycie usuwa **jeden biezacy, oryginalny wpis z jego pliku**.
Wyjatek S-001: gdy Anki zwrocilo poprawny identyfikator utworzonej notatki, ale
pozniejsze zadanie potwierdzajace zawiodlo, aplikacja pokazuje konkretne zadanie,
blad i zakres nieudanej kontroli, po czym usuwa wpis i przechodzi dalej. Brak
odczytu nie oznacza, ze zawartosc jest bledna. Rzeczywista niezgodnosc odczytanych
pol/talii i bledy potwierdzenia aktualizacji nadal zatrzymuja przetwarzanie.
Dotyczy to tworzenia, aktualizacji i custom cards; wpis z ksiazki znika z pliku
tej ksiazki. Zapisanie `cause` dla oryginalnego `causes` usuwa ten wpis `causes`,
bez usuwania innych wystapien lub wariantow. Zapis w review nie zmienia list slow.

**Discard from queue** usuwa biezacy wpis bez zmiany Anki, takze gdy istniejaca
notatka juz wystarcza. Nie ma osobnego **Skip** ani **Keep existing card**.
Widoczny przy istniejacej notatce przycisk **Discard card from queue** wykonuje
dokladnie te sama operacje co dolny **Discard from queue**. Zastapil zawieszanie
kart; zaden z tych przyciskow nie zmienia notatki ani dostepnosci kart w nauce.
Wyjscie przed rozstrzygnieciem slowa pozostawia je w pliku. Usunieto tez
**Delete duplicate note**; nadpisywanie odbywa sie przez aktualizacje w miejscu.

Historia pozostaje w lokalnej bazie SQLite: `note_index` zawiera powiazanie
slowo → notatka, `word_saves` zapis oczekiwanej/odczytanej zawartosci i stan
operacji, a `source_resolutions` dokladny usuniety wpis, wynik i dane do wznowienia.
Kopia pliku sprzed zmiany trafia do `data/archives/source-<entry-id>.txt.bak`.
Blokada wspolna z CLI chroni rownolegle dopisywane slowa. Identyfikator wpisu
blokuje zadania ze starego widoku; porownanie pliku i trwale potwierdzenie usuniecia
chronia kolejne identyczne wystapienie przy ponowieniu po awarii. Niejednoznaczna
zewnetrzna zmiana zachowuje plik i wymaga sprawdzenia zrodla/kopii zapasowej.

Brak potwierdzenia samego utworzenia (bez poprawnego `noteId`) pozostawia wpis
do dotychczasowego odzyskania; aplikacja nie tworzy slepo duplikatu. Utworzenie
zaakceptowane bez odczytu kontrolnego jest zapisane jako `acknowledged`, nie
`verified`, wraz z ostrzezeniem. Ten wyjatek nie uprawnia do zbiorczego czyszczenia.

Nieudane usuniecie z pliku jest raportowane jako `cleanupPending`. Widok pokazuje
przyczyne i przycisk **Retry queue removal** zamiast ponownego tworzenia notatki.
Kliknij go, aby ponowic tylko lokalne usuniecie oryginalnego wpisu: bez tworzenia,
odczytu kontrolnego, flagowania ani synchronizacji Anki. Widok ten wraca tez po
ponownym otwarciu zrodla. Sam blad pobrania potwierdzenia nie wymaga tego klikniecia
— tylko dodatkowy blad usuniecia wpisu. Synchronizacja z AnkiWeb nie jest warunkiem
lokalnego potwierdzenia.

Z dzialajacym Anki mozna tez oczyscic historyczne wpisy (po dokladnym dopasowaniu
`en_word`, bez porownywania dawnych tlumaczen z nieistniejacym payloadem):

```bash
python -m tools.clean_words_to_add                 # tylko raport
python -m tools.clean_words_to_add --apply         # odczyt kontrolny, archiwum, usuniecie
python -m tools.clean_words_to_add --apply --resume # wznowienie niedokonczonych operacji
```

To oddzielna, jawna operacja zbiorcza na glownej liscie. `--resume` wznawia tylko
jej operacje `already_in_anki`, nie zapisy biezacych zrodel ani review.

Migracja Q-001 (2026-11-21): dopisano na koncu glownego pliku 25 zatwierdzonych slow
obecnych tylko w starej kolejce SQLite, zachowano ustawienia celu i wycofano kopie
kolejki. Lokalna kopia bazy: `data/archives/pre-q001-20261121.sqlite3`.

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
pomijane, nadmiarowe spacje nie tworza nowych zasobow. Wielkosc liter jest
zachowywana w zadaniach i kluczach cache, aby nie mieszac `Polish`/`polish`.
Bezpieczne aliasy korzystaja z istniejacych lokalnych danych bez odswiezania.
Listy nie
sa modyfikowane przez downloader. Wgranie pliku tylko przez przegladarke nie
kopiuje go automatycznie do tego folderu.

Proces tla konczy kazde slowo w kolejnosci **HTML → MP3**, zanim przejdzie do
nastepnego. Uzywa jednej sesji HTTP w obrebie partii (cookies i polaczenia sa
ponownie wykorzystywane). Cookies nie sa eksportowane ani zapisywane na dysku.
Nagrania sa wybierane z linkow w zapisanym HTML: najpierw dokladne haslo,
potem wariant rozniacy sie tylko spacjami (np. `eyepatch` → `eye patch`).
Dla kazdej pisowni preferowane jest nagranie brytyjskie, potem amerykanskie.
Nagranie musi nalezec do rozstrzygnietego hasla Diki. Nowe pliki mediow Anki dla
hasel z wielkimi literami maja deterministyczny sufiks skrotu, aby uniknac kolizji
nazw `Polish`/`polish` na macOS; zapis `en_word` pozostaje oryginalnym haslem.
Nie wybieramy innych synonimow ani nagran przykladowych zdan i nie zgadujemy
nazw plikow. Brak linku oznacza brak dostepnego nagrania, bez szesciu prob HTTP.
Stare wpisy `no_audio` sa automatycznie sprawdzane nowa metoda z lokalnego HTML.
Zmiana HTML lub wersji selektora pozwala ponownie sprawdzic ujemny wynik.

Poczatkowy odstep procesu tla to 20 sekund +/- 5 sekund po zakonczeniu kazdego
zadania. HTTP 403/429 lub wykryty challenge podwajaja bazowy odstep (maks. 16×)
i wstrzymuja dane pobieranie na 6 godzin, potem 12 i maks. 24 godziny przy
kolejnych blokadach. Dluzszy `Retry-After` ma pierwszenstwo. Pierwsze zadanie po
pauzie jest proba wznowienia; po sukcesie partia kontynuuje ze zwiekszonym
odstepem. Kazde 10 poprawnych odpowiedzi z rzedu zmniejsza mnoznik o polowe,
do poziomu bazowego. Stan adaptacji i odstepow przetrwa restart. Nie ma arbitralnego
limitu dziennego ani godzinowego. Limit 600 sekund obejmuje czekanie, wiec partia
moze zakonczyc sie przed 25 slowami i wznowic brakujace nagranie w kolejnym przebiegu.

CLI i glowna aplikacja uzywaja profilu `interactive`; prefetch uzywa `background`.
Profile wspoldziela dobre pliki cache, ale maja osobne sesje, blokady zadaniowe,
odstepy, cooldowny i retry bledow sieciowych. Interaktywne zadania nie maja
odstepu scraperowego i nie czekaja za jego kolejka. Stary globalny cooldown i
bledy sa jednorazowo przenoszone do profilu tla; dobre pliki pozostaja bez zmian.
Oba profile nadal lacza sie z tego samego publicznego IP — nie jest to separacja
sieciowa ani implementacja proxy.

Bledy polaczenia zatrzymuja dany profil na 5 minut. Pojedynczy `ReadTimeout` lub
5xx odklada dane slowo; trzy takie bledy z rzedu zatrzymuja partie na 5 minut.
Inne bledy HTTP lub nieprawidlowe odpowiedzi wstrzymuja pobieranie na co najmniej
30 minut. Retry zasobu rosnie od 30 minut do 24 godzin, ale samo sprawdzenie
aktywnej pauzy nie zwieksza liczby bledow slowa. Bledne odpowiedzi nie zastepuja
dobrego cache. Poprawne strony 404 z sugestiami sa zapisywane bez pobierania MP3.

Raport rozroznia nowa blokade (`cooldown`) od pozniejszego przebiegu bez zadan
(`paused`). Pokazuje mnoznik odstepu oraz liczniki wykrytych challenge i HTTP 429.
W bazie pozostaje ostatnich 1000 zdarzen HTTP: profil, URL, status, czas,
wybrane naglowki (`Content-Type`, `Retry-After`, `CF-Ray`, `CF-Mitigated`),
tytul i powod klasyfikacji. Nie zapisujemy tresci challenge ani cookies/tokenow.
HTTP 524 jest bledem serwera zrodlowego, a nie samodzielnym dowodem blokady.
Zwykly skrypt Cloudflare obok poprawnego slownika nie oznacza challenge.

Terminalowy `diki <word>` pokazuje prosty wskaznik pobierania i ma limit
30 sekund na lookup, obejmujacy blokady, DNS i odczyt calej odpowiedzi.
Limit nie obejmuje czekania na odpowiedz uzytkownika przy wyborze/zapisie slowa.

`--refresh` jawnie odswieza zasoby, w tym potwierdzone braki, w granicach podanej
partii. Nadal respektuje odstepy i cooldown swojego profilu. Przy odswiezaniu wybranych
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
python -m tools.test_offline
```

Testy korzystaja z zapisanych stron, atrap HTTP/Anki i plikow tymczasowych.
Runner blokuje polaczenia i DNS oraz wylacza testy live niezaleznie od odziedziczonych
zmiennych srodowiskowych. Nie wlacza aplikacyjnego `DIKI_OFFLINE=1`, bo testy
pobierania musza przechodzic przez sciezke atrap HTTP. Bezposrednie uruchomienie
`unittest` omija blokade runnera; jest przeznaczone m.in. do jawnych testow
integracyjnych (`RUN_LIVE_DIKI_TESTS=1` dla dwoch testow Diki).

## Dane lokalne

- `data/anki_flashcards_factory.sqlite3` - indeks notatek i sesje.
- `data/diki_cache/` - HTML, MP3 i osobna baza metadanych, odstepow i postepu pobierania.
- `words_to_add/words_to_add.txt` - opcjonalna lista slow do zaimportowania w kolejnosci linii.

Preprocessing `raw_notes/` / `prepared_notes/`, raw editor i opcja `--app -e`
zostaly usuniete. Usunieto tez reczna obsluge indeksu przez `main.py --db`
oraz eksport MP3 bezposrednio do folderu mediow. Audio trafia do aktywnego profilu
Anki przez AnkiConnect; `ANKI_MEDIA_FOLDER_PATH` i `ANKI_BASE_DECK_PATH` nie sa
juz uzywane. Szczegoly: [zakonczone wycofanie starszych sciezek](docs/features/maintenance-and-tooling.md#legacy-code-cleanup-and-obsolete-tests-t-001).

Starszy indeks JSON ustawiony przez `DATABASE_PATH` jest jednokrotnie
importowany do SQLite przy pierwszym uruchomieniu.

## Migracja kontraktow danych notatek (w toku)

Cel, zasady parsowania pol, iteracyjny workflow oraz punkt wznowienia prac sa w
[Note data contracts — Migration](note-data-contracts.md#migration).
Dokument opisuje tez zakonczona migracje 44 notatek obrazkowych do
`TEMP Image recall`, wylaczenia z kontraktow i pozostale pola do opracowania.

Aktualny audyt tylko do odczytu (na razie sprawdza wylacznie `en_word`):

```bash
python -m tools.audit_note_contracts --sample-size 10
```
