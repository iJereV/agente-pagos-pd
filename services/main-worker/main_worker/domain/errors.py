"""Error classes that drive the Pub/Sub acknowledgement policy.

- ``PermanentError``: retrying cannot help; the message is logged and acknowledged.
- ``TransientError``: retrying may help; the push is answered with 5xx.
Any other exception is treated as transient too.
"""


class PermanentError(Exception):
    """The message can never be processed (malformed, rejected by a third party)."""


class TransientError(Exception):
    """A dependency failed temporarily (timeouts, 5xx, rate limits)."""


class SessionNotFound(Exception):
    """The agent session referenced by the pointer no longer exists."""
