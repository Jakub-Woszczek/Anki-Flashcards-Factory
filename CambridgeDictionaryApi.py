import requests
from bs4 import BeautifulSoup


class CambridgeDictionaryApi:
    def __init__(self):
        self.definition_url = "https://dictionary.cambridge.org/dictionary/english/" # Add english word to this url
    
    
    def get_definition(self, word):
        response = requests.get(self.definition_url + word)
        html = response.text
        
        soup = BeautifulSoup(html, 'html.parser')
        
        print(soup)