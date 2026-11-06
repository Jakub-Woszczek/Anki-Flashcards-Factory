import tempfile
from pathlib import Path
from unittest import TestCase

from backend.services import FactoryService


class FakeDiki:
    last_error = None

    def __init__(self, audio_path: Path):
        self.audio_path = audio_path
        self.last_audio_path = None

    def diki_audio_harness(self, _word):
        self.last_audio_path = str(self.audio_path)
        return True


class FakeAnki:
    last_error = None

    def store_media_file(self, filename, content):
        self.call = (filename, content)
        return filename


class TestAudioSync(TestCase):
    def test_downloaded_audio_is_stored_in_ankis_active_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "self-loathing.mp3"
            audio_path.write_bytes(b"audio")
            service = FactoryService.__new__(FactoryService)
            service.diki = FakeDiki(audio_path)
            service.anki = FakeAnki()

            self.assertTrue(service._write_audio("self-loathing"))
            self.assertEqual(service.anki.call, ("self-loathing.mp3", b"audio"))
