import os
from dotenv import load_dotenv

load_dotenv()

MERRIAM_WEBSTER_DIC_API = os.getenv("MERRIAM_WEBSTER_DIC_API")

if not MERRIAM_WEBSTER_DIC_API:
    raise ValueError("Brak klucza MERRIAM_WEBSTER_DIC_API w zmiennych środowiskowych")
