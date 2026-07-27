"""Tests for the Celery beat scheduler configuration (RedBeat)."""

from django.conf import settings

from task_processor.celery import app


def test_beat_scheduler_is_redbeat():
    assert app.conf.beat_scheduler == "redbeat.RedBeatScheduler"


def test_redbeat_redis_url_defaults_to_broker():
    assert app.conf.redbeat_redis_url == settings.CELERY_REDBEAT_REDIS_URL
    assert app.conf.redbeat_redis_url.startswith("redis://")


def test_redbeat_scheduler_importable():
    from redbeat import RedBeatScheduler  # noqa: F401
