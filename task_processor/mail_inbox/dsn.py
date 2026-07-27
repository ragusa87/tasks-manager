"""Parsing of the EMAIL_INBOX_DSN setting.

Supported forms:
    smtp://0.0.0.0:2525?max_size=10485760       local SMTP server
    imap://user:pass@host:143/INBOX?poll=60     remote IMAP polling (plaintext)
    imaps://user:pass@host:993/INBOX?poll=60    remote IMAP polling over TLS

An '@' cannot appear in the DSN userinfo (it would split off a host), so the
IMAP login name is completed by appending the inbox domain by default:
'inbox-x' -> 'inbox-x@<USER_EMAIL_INBOX_DOMAIN>'. Override with the
?domain_in_username option (see InboxDSN.login_username).

?dry_run=1 makes the IMAP engine read-only: it resolves and logs what it would
do with each message but never creates tasks or deletes mail.

Credentials are percent-decoded (urllib.parse.unquote), so reserved characters
in the username/password must be percent-encoded in the DSN. In particular a
literal '%' must be written as '%25' (e.g. a password '..%lV..' -> '..%25lV..'),
otherwise it is interpreted as the start of a %XX escape.
"""

from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

KNOWN_SCHEMES = ("smtp", "imap", "imaps")
SSL_SCHEMES = ("imaps",)
DEFAULT_PORTS = {"smtp": 2525, "imap": 143, "imaps": 993}
DEFAULT_SMTP_PORT = 2525
DEFAULT_MAX_SIZE = 10 * 1024 * 1024
DEFAULT_MAILBOX = "INBOX"
DOMAIN_IN_USERNAME_OPTION = "domain_in_username"
FALSEY = ("0", "false", "no", "off", "")
TRUTHY = ("1", "true", "yes", "on")


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

    @property
    def use_ssl(self):
        return self.scheme in SSL_SCHEMES

    @property
    def mailbox(self):
        """The IMAP mailbox to poll, taken from the URL path (default INBOX)."""
        return self.path.strip("/") or DEFAULT_MAILBOX

    @property
    def dry_run(self):
        """Read-only mode: log intended actions, create no tasks, delete no mail."""
        return str(self.options.get("dry_run", "")).strip().lower() in TRUTHY

    def login_username(self, default_domain):
        """The username to authenticate the IMAP session with.

        Because the DSN userinfo can't hold an '@', the domain is appended here.
        Controlled by the ?domain_in_username option. The leading '@' is
        optional — both forms give the same result:
            absent                append '@<default_domain>'
            0 / false / no / off  use the username verbatim (no domain)
            @constantin.dev       -> 'inbox-x@constantin.dev'
            constantin.dev        -> 'inbox-x@constantin.dev'
        """
        if self.username is None:
            return None
        option = self.options.get(DOMAIN_IN_USERNAME_OPTION)
        if option is None:
            suffix = f"@{default_domain}"
        elif option.strip().lower() in FALSEY:
            return self.username
        else:
            # Accept the domain with or without a leading '@'.
            suffix = option if option.startswith("@") else f"@{option}"
        return f"{self.username}{suffix}"


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
        port = DEFAULT_PORTS[parsed.scheme]

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
