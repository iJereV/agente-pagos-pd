"""Receipts: raw text extracted by a model, parsed into facts by code."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from mcp_shop.domain.money import parse_argentine_amount

ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}  # fmt: skip
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{4}|\d{2})\b")
_SPANISH_DATE = re.compile(
    r"\b(\d{1,2})\s+(?:de\s+)?([a-záéíóú]{3,})\.?\s+(?:de(?:l)?\s+)?(\d{4})\b", re.IGNORECASE
)
_TIME = re.compile(
    r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(?:(a|p)\.?\s*m\.?)?(?![\w:])", re.IGNORECASE
)


@dataclass(frozen=True)
class RawReceipt:
    """Fields exactly as printed on the receipt. The model copies; it never computes."""

    is_receipt: bool
    coelsa_id: str | None = None
    amount_text: str | None = None
    datetime_local_text: str | None = None
    origin_cuit: str | None = None
    destination_cvu: str | None = None
    bank_name: str | None = None


@dataclass(frozen=True)
class ParsedReceipt:
    coelsa_id: str | None
    amount_cents: int | None
    sent_at: datetime | None
    origin_cuit: str | None


def parse_receipt(raw: RawReceipt) -> ParsedReceipt:
    return ParsedReceipt(
        coelsa_id=normalize_id(raw.coelsa_id) if raw.coelsa_id else None,
        amount_cents=parse_argentine_amount(raw.amount_text) if raw.amount_text else None,
        sent_at=parse_local_datetime(raw.datetime_local_text) if raw.datetime_local_text else None,
        origin_cuit=normalize_cuit(raw.origin_cuit),
    )


def normalize_id(value: str) -> str:
    """Drop whitespace and dashes and upper-case. Characters themselves are never changed."""
    return re.sub(r"[\s-]", "", value).upper()


def normalize_cuit(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    return digits if len(digits) == 11 else None


def parse_local_datetime(text: str) -> datetime | None:
    """Parse an Argentine local date and time (as printed) into an aware UTC datetime."""
    date = _parse_date(text)
    time = _parse_time(text)
    if date is None or time is None:
        return None
    year, month, day = date
    hour, minute, second = time
    try:
        local = datetime(year, month, day, hour, minute, second, tzinfo=ARGENTINA_TZ)
    except ValueError:
        return None
    return local.astimezone(UTC)


def _parse_date(text: str) -> tuple[int, int, int] | None:
    if numeric := _NUMERIC_DATE.search(text):
        day, month, year = (int(group) for group in numeric.groups())
        return (2000 + year if year < 100 else year), month, day
    if spanish := _SPANISH_DATE.search(text):
        named_month = _MONTHS.get(spanish.group(2)[:3].lower())
        if named_month is not None:
            return int(spanish.group(3)), named_month, int(spanish.group(1))
    return None


def _parse_time(text: str) -> tuple[int, int, int] | None:
    found = _TIME.search(text)
    if found is None:
        return None
    hour, minute = int(found.group(1)), int(found.group(2))
    second = int(found.group(3) or 0)
    meridiem = (found.group(4) or "").lower()
    if meridiem == "p" and hour < 12:
        hour += 12
    elif meridiem == "a" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59 or second > 59:
        return None
    return hour, minute, second
