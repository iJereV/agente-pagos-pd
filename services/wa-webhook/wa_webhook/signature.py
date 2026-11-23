"""Meta webhook signature check (``X-Hub-Signature-256``)."""

import hashlib
import hmac

_PREFIX = "sha256="


def is_valid_signature(raw_body: bytes, header: str | None, app_secret: str) -> bool:
    """True when ``header`` is the HMAC-SHA256 of the raw body with the app secret."""
    if not header or not header.startswith(_PREFIX):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix(_PREFIX))
