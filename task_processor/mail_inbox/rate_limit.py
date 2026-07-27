"""Cache-based rate limiting for the mail inbox.

Fixed-window counters keyed on the sender address and/or the target inbox.
Fails open (allows the message) when the configured cache backend does not
support atomic counters (e.g. DummyCache), so a cache outage never turns
into a mail outage.
"""

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("task_processor.mail_inbox")


def _digest(value):
    return hashlib.sha1(value.strip().lower().encode()).hexdigest()


class RateLimiter:
    def __init__(self, limits=None):
        self.limits = limits if limits is not None else settings.EMAIL_INBOX_RATE_LIMITS

    def hit(self, sender, inbox_id=None):
        """Record one message and report whether any limit is exceeded.

        With inbox_id=None only the per-sender limit is checked; this runs
        before recipient resolution so that bulk probing is throttled without
        leaking whether an address exists.
        """
        checks = [("per_sender", f"s:{_digest(sender)}")]
        if inbox_id is not None:
            checks += [
                ("per_sender_recipient", f"sr:{_digest(sender)}:{inbox_id}"),
                ("per_recipient", f"r:{inbox_id}"),
            ]

        exceeded = False
        for limit_name, key in checks:
            if limit_name not in self.limits:
                continue
            max_count, window = self.limits[limit_name]
            if self._hit_one(f"mailinbox:rl:{key}", max_count, window):
                logger.info("Rate limit %s exceeded for key %s", limit_name, key)
                exceeded = True
        return exceeded

    def _hit_one(self, key, max_count, window):
        try:
            cache.add(key, 0, timeout=window)
            count = cache.incr(key)
        except (ValueError, NotImplementedError):
            logger.warning(
                "Cache backend does not support counters, "
                "mail inbox rate limiting is disabled"
            )
            return False
        return count > max_count
