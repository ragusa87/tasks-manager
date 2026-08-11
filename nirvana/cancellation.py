"""Cross-process cancellation flags for running Nirvana imports.

The web process sets a flag in the shared cache (Redis); the Celery worker
checks it between progress writes and aborts the import when it appears.
Ownership is enforced by the view before a flag is ever set — the worker
only ever sees flags for its own job id.
"""

from django.core.cache import cache

# Outlives any reasonable import; a stale flag for a finished job is harmless
# because it is keyed by job id and cleared when the job ends.
CANCEL_FLAG_TTL = 60 * 60


def _key(job_id):
    return f"nirvana-import:cancel:{job_id}"


def request_cancellation(job_id):
    cache.set(_key(job_id), True, timeout=CANCEL_FLAG_TTL)


def is_cancellation_requested(job_id):
    return bool(cache.get(_key(job_id)))


def clear_cancellation(job_id):
    cache.delete(_key(job_id))
