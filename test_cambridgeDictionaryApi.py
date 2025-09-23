from unittest import TestCase

from CambridgeDictionaryApi import CambridgeDictionaryApi


class TestcambridgeDictionaryApi(TestCase):
    def setUp(self):
        self.dictApi = CambridgeDictionaryApi()
    
    def test_get_definition(self):
        self.dictApi.get_definition("uninhalited")
        
