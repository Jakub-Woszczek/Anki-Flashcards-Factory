from unittest import TestCase

from backend.services import FactoryService


class FakeAnki:
    last_error = None

    def __init__(self):
        self.sync_calls = 0

    def sync(self):
        self.sync_calls += 1
        return True


class FailingAnki(FakeAnki):
    def sync(self):
        self.sync_calls += 1
        self.last_error = "AnkiWeb is unavailable"
        return False


class TestSyncRateLimit(TestCase):
    def make_service(self, anki):
        service = FactoryService.__new__(FactoryService)
        service.anki = anki
        self.now = 0.0
        service._sync_clock = lambda: self.now
        return service

    def test_syncs_immediately_then_waits_ten_seconds_between_attempts(self):
        anki = FakeAnki()
        service = self.make_service(anki)

        self.assertTrue(service._sync_after_mutation()["synced"])
        self.now = 4.0
        self.assertTrue(service._sync_after_mutation()["syncPending"])
        self.now = 9.0
        self.assertTrue(service._sync_after_mutation()["syncPending"])
        self.now = 19.0
        self.assertTrue(service._sync_after_mutation()["synced"])

        self.assertEqual(anki.sync_calls, 2)

    def test_failed_sync_is_rate_limited_and_remains_pending(self):
        anki = FailingAnki()
        service = self.make_service(anki)

        result = service._sync_after_mutation()
        self.assertEqual(result["syncWarning"], "AnkiWeb is unavailable")
        self.now = 4.0
        self.assertTrue(service._sync_after_mutation()["syncPending"])

        self.assertEqual(anki.sync_calls, 1)

    def test_flush_sync_bypasses_the_rate_limit(self):
        anki = FakeAnki()
        service = self.make_service(anki)

        service._sync_after_mutation()
        self.now = 4.0
        service._sync_after_mutation()
        result = service.flush_sync()

        self.assertTrue(result["synced"])
        self.assertEqual(anki.sync_calls, 2)
