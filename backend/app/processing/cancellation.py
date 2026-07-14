from __future__ import annotations


class JobCancelledError(Exception):
    """Raised inside pipeline work when the user has requested cancellation."""
