IMPROVMENT_REQUEST = """
Poniżej jet fiszka, twoim zadaniem jest ocenić czy dana fiszka jest poprawnie zrobiona.
-  Czy tłumaczenie jest poprawne (czy nie jest przestarzałe, literackie, nieużywane, itp.)
   Jeżeli jest, to napisz wersję fiszki bez złych tłumaczeń
-  Czy nie ma literówek, jeżeli ma to odpowiedz 'MISSSPELL#slowo#'
-  Jeśli słowo można przedstawić graficznie w jakikolwiek pomocny sposób, odpowiedz 'IMAGE'
-  Synonimy: Zredukuj listę synonimów do 1-3 najtrafniejszych
-  Jeżeli fiszka jest pusta, napisz 'ERROR'
-  Popraw błędy ortograficzne, gramatyczne

Jeżeli mam slash, czyli '/', to oddzielają one przymiotnik/rzeczownik od czasownika

Uwagi wymień po przecinku (jeżeli są, jeżeli nie to nie pisz nic)
Po nimi napisz poprawną wersję fiszki (jeżeli coś zmieniłeś, jeżeli nie to nie pisz)
Jeżeli nie masz uwag i nic nie zmieniłeś, napisz tylko 'OK'
Kolejność polskiego i angielskiego słowa ma być taka jak w fiszce

Przykłady:

Zapytanie - <czubek góry lodowej, wierzchołek góry lodowej><the tip of the iceberg>
Odpowiedź - <wierzchołek góry lodowej><the tip of the iceberg>
(powtarzające się synonimy)

Zapytanie - <złapać, chwycić, chapnąć,porwać><snatch>
Odpowiedź - <chwycić, porwać><snatch>
(powtarzające się synonimy)

Zapytanie - <stawać na baczność><stand at attention>
Odpowiedź - IMAGE<stawać na baczność><stand at attention>

Zapytanie - <obłąkaniec, szaeniec, wariat><luatic>
Odpowiedź - MISSSPELL#szaeniec#MISSSPELL#luatic#,<szaleniec><lunatic>

to jest moja fiszka: """

BOT_QUESTION_IMAGE = """
Fiszke można przedstawić graficznie jeżeli jest to przedmiot lub jakiś
nieabstrakcyjny czasownik lub rzeczowik.

Mam fiszke, jeżeli da się przedstawić graficznie tą fiszke zamiast słownie, to odpisz 'TRUE',
jeżeli nie to odpisz 'FALSE'

Fiszka: """

BOT_QUESTION_SPELLING = """
Jeżeli w tej fiszce występują literówki to napisz:
<błędne słowo:poprawne słowo><błędne słowo2:poprawne słowo2> itd...
Jeżeli nie występują literówki napisz tylko 'OK'

Przykład poprawy literówki:
<catt:cat><pozonie:pozornie>

Fiszka: """

BOT_QUESTION_SIMPLIFY = """
Mam fiszke, mogą w niej wystąpić niepotrzebne synonimy jakiś słów (które nieopatrznie dodałem),
jeżeli występują to wybierz tylko jeden z nich który najlepiej oddaje tłumaczenie, jeżeli synonimy
nie występują odpisz 'OK'

Przykład:

fiszka: <łączyć, scalać, zlewać, zmieszać><merge>
odpowiedź: <łączyć, zmieszać><merge>

moja fiszka: """

ALL_BOT_QUESTIONS = [BOT_QUESTION_IMAGE, BOT_QUESTION_SPELLING, BOT_QUESTION_SIMPLIFY]