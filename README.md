# 🃏 Anki Flashcards Factory

> Automatyczne tworzenie fiszek angielsko-polskich na podstawie tłumaczeń z Diki.pl, zarządzane przez AnkiConnect.

---

## 💡 Idea

Uczysz się angielskiego i po drodze notujesz słówka, które napotykasz – w książkach, podcastach, filmach. Z czasem zbierasz listę angielskich słów:

```
ephemeral
sanguine
juxtapose
...
```

Apka stowrzy fiszki:  **angielskie słowo - polskie tłumaczenia**

1. Wklej listę słów
2. Zaznacz wybrane (SLASH - stworzy 'enter' (`\n`) między słówkami)
3. Możesz zapytać się o definicje Gemini/ dodać tagi do fiszek
4. Aplikacja sama stworzy taką fiszke i ją zapisze

### Dodatkowa logika weryfikacji pisowni

Niektóre słowa mogą być zapisane w Twoich notatkach inaczej niż występują na Diki.pl. Zaimplementowałem funkcjonalość gdzie możesz wkelić liste słówek do `raw_notes/input.txt` i z tamtąd wstępnie aplikacja przetworzy je na 2 pliki (gdzie w `input_correct` KAŻDE słówko jest poprawne): 

| Plik                | Zawartość                                         |
|---------------------|---------------------------------------------------|
| `input_correct.txt` | Słowa istniejące w diki (lub po poprawie pisowni) |
| `errors.txt`        | Słówka nie istniejące w diki                      |

[Komenda uruchomienia](#31-edycja-poprawnych-słówek)

---

## Jak używać

### 1. Stwórz środowisko wirtualne
```bash
python3 -m venv venv # Drugi arg to ścieżka
```

### 1.1 Uruchom środowisko wirtualne

**macOS / Linux:**
```bash
source .ankiFact/bin/activate
```

**Windows:**
```bash
.ankiFact\Scripts\activate
```

---

### 2. Pobierz zależności
```bash
pip install -r requirements.txt
```

### 2.1 Pobierz tkinter (jeżeli nie masz)

<details>
<summary>Jak sprawdzić czy masz tkinter (Windows instaluje domyślnie przeważnie)</summary>

```bash
python -m tkinter # Powinno małe okienko wyskoczyć
```

</details>

### 3. Skonfiguruj zmienne środowiskowe

Utwórz plik `.env` w głównym katalogu projektu i uzupełnij poniższe wartości:

```bash
# Ścieżka do folderu mediów Anki
# macOS (domyślna):
ANKI_MEDIA_FOLDER_PATH='/Users/{twoja_nazwa_użytkownika}/Library/Application Support/Anki2/Użytkownik 1/collection.media'

# Port AnkiConnect (domyślnie 8765)
ANKI_URL=http://127.0.0.1:8765

# Klucz API Gemini – uzyskaj na: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=

# Ścieżki do plików roboczych
PREPARED_WORDS_PATH=prepared_notes/diki_prepared.txt
PREPROCESSED_WORDS_FILE=input.txt
DIKI_MISSING_WORDS_PATH=raw_notes/diki_missing.txt
ERROR_WORDS_PATH=raw_notes/errors.txt

# Ścieżka do talii w Anki (poziomy oddzielone ::)
# Przykład: talia nadrzędna "English", docelowa talia "A1"
ANKI_DECK_PATH=English::A1
ANKI_DECK_PATH_TEST=English::test

# Ścieżka do pliku testowego
TEST_WORDS_PATH=test_words
```
- ❗️ Musisz sprawdzić ścieżkę do folderu z mediami aplikacji Anki
- ❗️ Musisz dodać swój API key gemini (jeżeli chcesz korzystać z AI assistant — niewymagane do działania głównej logiki aplikacji)
---

### 3. Uruchomienie
#### 3.1 Preprocessing słówek
```bash
python main.py --app -e
```

<details>
<summary>Przykład przebiegu preprocessingu</summary>

```bash
~/sidePrjs/ankiFac main* ⇡ 8s                                                                                                                          15:38:19
.ankiFact ❯ python main.py --app -e
CHECK rookie mistake
Słowo: rookie mistake ✔
CHECK commerce
Słowo: commerce ✔
CHECK cite
Słowo: cite ✔
CHECK intrinsicaly
Możliwe poprawne wersje [intrinsicaly]:
1. intrinsically
Wybierz numer poprawnej wersji (0 = pomiń): 1
→ Zapisano: intrinsically
CHECK on it's own
→ Słówko nie istnieje w diki ani nie ma podobnych
```
</details>

#### 3.2 Główna aplikacja: tworzenie fiszek
```bash
python main.py --app
```
Uruchamia główną aplikację

➡️ Aplikacja prowadzi lokalną bazę danych, która zapobiega duplikatom fiszek.

## ❗️Uwagi
Należy przygotować w samej aplikacji Anki/zmienić w kodzie - to jak się nazywają pola fiszki, jak się nazywa model fiszki.
Kod do tego znajduje się w funkcji `add_flashcard`, który wywołuje RPC `add_flashcard`.

## ⚠️ Wymagania

- Uruchomione **Anki** z zainstalowanym pluginem [AnkiConnect](https://ankiweb.net/shared/info/2055492159)
- Python 3.x ze środowiskiem wirtualnym
- Klucz API Gemini (opcjonalnie, do generowania definicji)
- (przydatne) znajomość Pythona
- znajomość Anek (od technicznej strony: pola/typy fiszek/...)
---

## Inne

#### Struktura projektu

```
anki-flashcards-factory/
├── raw_notes/
│   ├── input.txt           # Orginalna lista słówek
│   ├── input_correct.txt    # Przetworzona lista słówek
│   └── errors.txt          # Słowa nieznalezione w diki
├── prepared_notes/
│   └── diki_prepared.txt   # Gotowe słowa tworzenia fiszek
├── test_words/             # Dane testowe
└── .env                    # Konfiguracja (utwórz samodzielnie)
```

---

#### Przestarzałe

Poniższe zmienne środowiskowe nie są już używane i można je pominąć:

```env
DATABASE_PATH=db/flashcards_db.json  # wycofane – użyte do allNotesDb
ANKI_BASE_DECK_PATH=English          # wycofane
DIKI_MISSING_WORDS_PATH=raw_notes/diki_missing.txt
```