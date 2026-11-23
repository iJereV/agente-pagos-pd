"""Sortable order ids (`ord_` + ULID) and the clock, injectable for tests."""

import secrets
from datetime import UTC, datetime

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_order_id() -> str:
    """`ord_` followed by a ULID: 48-bit millisecond time plus 80 random bits."""
    millis = int(datetime.now(UTC).timestamp() * 1000)
    value = (millis << 80) | secrets.randbits(80)
    chars = []
    for _ in range(26):
        value, index = divmod(value, 32)
        chars.append(_CROCKFORD[index])
    return "ord_" + "".join(reversed(chars))


def utc_now() -> datetime:
    return datetime.now(UTC)
