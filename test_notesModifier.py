from unittest import TestCase
from notesModifier import NotesImprovement


class TestNotesImprovement(TestCase):

    def setUp(self):
        self.parser = NotesImprovement()

    def test_spellcheck(self):
        test_case1 = "bardzo zajęty, zawalony robotą/ zalewać (okolicę), zatapiać (np. statek), zanurzać (się w wodzie, bagnie)"
        test_case2 = (
            "popołudniowe przedstawienie, popołudniowy seans (kino, teatr, itp.) "
        )

        self.parser.spellcheck_pl(test_case1)
        self.parser.spellcheck_pl(test_case2)

    def test_spellcheck_pl(self):

        test_case1 = "bardzo zajety, zwalony robotą/ zalewać (okolicę), zatapiać (np. statek), zanurzać (się w wodzie, bagnie)"
        test_case2 = "popołudniowe predstawienie, popołudnioy sans (kino, teatr, itp.) "
        # test_case3 = "zlo"

        print(self.parser.spellcheck_pl(test_case1))
        print(self.parser.spellcheck_pl(test_case2))
        # print(self.parser.spellcheck_pl(test_case3))

    def test_split_words_pl(self):
        test_case1 = "bardzo zajety, zwalony robotą/ zalewać (okolicę), zatapiać (np. statek), zanurzać (się w wodzie, bagnie)"

        print(self.parser.split_words_pl(test_case1))

    def test_images_improvement(self):
        self.parser.images_improvement("C2[Obrazkowe]")
