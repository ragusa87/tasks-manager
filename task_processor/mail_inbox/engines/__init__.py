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
    raise CommandError(
        f"Engine {dsn.scheme!r} is not implemented yet (only 'smtp' is available)"
    )
