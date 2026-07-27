"""Parsing of the EMAIL_INBOX_DSN setting.

Supported forms:
    smtp://0.0.0.0:2525?max_size=10485760      local SMTP server
    imaps://user:pass@host:993/INBOX?poll=60   remote IMAP polling (future)
"""

from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

KNOWN_SCHEMES = ("smtp", "imap", "imaps")
DEFAULT_SMTP_PORT = 2525
DEFAULT_MAX_SIZE = 10 * 1024 * 1024


@dataclass(frozen=True)
class InboxDSN:
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    path: str = ""
    options: dict = field(default_factory=dict)

    @property
    def max_size(self):
        try:
            return int(self.options.get("max_size", DEFAULT_MAX_SIZE))
        except (TypeError, ValueError):
            raise ImproperlyConfigured(
                f"EMAIL_INBOX_DSN: max_size must be an integer, "
                f"got {self.options.get('max_size')!r}"
            )

    @property
    def poll_interval(self):
        try:
            return int(self.options.get("poll", 60))
        except (TypeError, ValueError):
            raise ImproperlyConfigured(
                f"EMAIL_INBOX_DSN: poll must be an integer, "
                f"got {self.options.get('poll')!r}"
            )


def parse_dsn(value):
    parsed = urlparse(value)
    if parsed.scheme not in KNOWN_SCHEMES:
        raise ImproperlyConfigured(
            f"EMAIL_INBOX_DSN: unknown scheme {parsed.scheme!r}, "
            f"expected one of {', '.join(KNOWN_SCHEMES)}"
        )
    if not parsed.hostname:
        raise ImproperlyConfigured("EMAIL_INBOX_DSN: host is required")
    try:
        port = parsed.port
    except ValueError:
        raise ImproperlyConfigured("EMAIL_INBOX_DSN: port must be an integer")
    if port is None:
        port = {"smtp": DEFAULT_SMTP_PORT, "imap": 143, "imaps": 993}[parsed.scheme]

    options = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
    return InboxDSN(
        scheme=parsed.scheme,
        host=parsed.hostname,
        port=port,
        username=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
        path=parsed.path,
        options=options,
    )
