"""Money parsing. Amounts are integer cents everywhere."""

import re
from decimal import Decimal, InvalidOperation

# Argentine format: dot for thousands, comma for decimals. "2.166,35", "2166,35", "2.166".
_ARGENTINE_AMOUNT = re.compile(r"^(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?$")
_NOISE = re.compile(r"\$|ARS|\s", re.IGNORECASE)


def parse_argentine_amount(text: str) -> int | None:
    """Parse an amount as printed on an Argentine receipt into cents.

    `"$ 2.166,35"` -> `216635`. Returns `None` when the text is not a positive amount
    in that format, so callers never guess.
    """
    cleaned = _NOISE.sub("", text)
    if not _ARGENTINE_AMOUNT.match(cleaned):
        return None
    units, _, decimals = cleaned.partition(",")
    cents = int(units.replace(".", "")) * 100 + int(decimals.ljust(2, "0") or "0")
    return cents if cents > 0 else None


def decimal_to_cents(value: str | float | Decimal) -> int:
    """Convert a provider decimal amount (for example `2166.35`) to exact cents."""
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"not a decimal amount: {value!r}") from error
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"amount has sub-cent precision: {value!r}")
    return int(cents)
