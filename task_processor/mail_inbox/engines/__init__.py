import abc

from django.core.management.base import CommandError


class BaseEngine(abc.ABC):
    @abc.abstractmethod
    def run(self):
        """Start the engine and block until stop() is called."""

    @abc.abstractmethod
    def stop(self):
        """Request a graceful shutdown."""


def build_engine(dsn, host=None, port=None):
    if dsn.scheme == "smtp":
        from .smtp import SmtpEngine

        return SmtpEngine(
            host=host or dsn.host,
            port=port or dsn.port,
            data_size_limit=dsn.max_size,
        )
    if dsn.scheme in ("imap", "imaps"):
        from django.conf import settings

        from .imap import ImapEngine

        return ImapEngine(
            host=host or dsn.host,
            port=port or dsn.port,
            username=dsn.login_username(settings.USER_EMAIL_INBOX_DOMAIN),
            password=dsn.password,
            mailbox=dsn.mailbox,
            poll_interval=dsn.poll_interval,
            use_ssl=dsn.use_ssl,
            dry_run=dsn.dry_run,
        )
    raise CommandError(
        f"Engine {dsn.scheme!r} is not implemented (available: 'smtp', 'imap', 'imaps')"
    )
