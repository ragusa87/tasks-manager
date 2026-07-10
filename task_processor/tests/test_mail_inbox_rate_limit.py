from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from task_processor.mail_inbox.rate_limit import RateLimiter

LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=LOCMEM_CACHE)
class RateLimiterTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_per_sender_limit_enforced(self):
        limiter = RateLimiter(limits={"per_sender": (2, 60)})
        self.assertFalse(limiter.hit("a@example.com"))
        self.assertFalse(limiter.hit("a@example.com"))
        self.assertTrue(limiter.hit("a@example.com"))

    def test_senders_are_independent(self):
        limiter = RateLimiter(limits={"per_sender": (1, 60)})
        self.assertFalse(limiter.hit("a@example.com"))
        self.assertFalse(limiter.hit("b@example.com"))
        self.assertTrue(limiter.hit("a@example.com"))

    def test_sender_matching_is_case_insensitive(self):
        limiter = RateLimiter(limits={"per_sender": (1, 60)})
        self.assertFalse(limiter.hit("a@example.com"))
        self.assertTrue(limiter.hit("A@Example.COM"))

    def test_per_recipient_limit_enforced(self):
        limiter = RateLimiter(limits={"per_recipient": (2, 60)})
        self.assertFalse(limiter.hit("a@example.com", inbox_id=1))
        self.assertFalse(limiter.hit("b@example.com", inbox_id=1))
        self.assertTrue(limiter.hit("c@example.com", inbox_id=1))

    def test_per_sender_recipient_limit_enforced(self):
        limiter = RateLimiter(limits={"per_sender_recipient": (1, 60)})
        self.assertFalse(limiter.hit("a@example.com", inbox_id=1))
        self.assertFalse(limiter.hit("a@example.com", inbox_id=2))
        self.assertTrue(limiter.hit("a@example.com", inbox_id=1))

    def test_recipient_limits_skipped_without_inbox(self):
        limiter = RateLimiter(limits={"per_recipient": (0, 60)})
        self.assertFalse(limiter.hit("a@example.com"))


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class RateLimiterFailOpenTests(SimpleTestCase):
    def test_fails_open_on_dummy_cache(self):
        limiter = RateLimiter(limits={"per_sender": (0, 60)})
        self.assertFalse(limiter.hit("a@example.com"))
