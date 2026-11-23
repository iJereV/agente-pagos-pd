from datetime import UTC, datetime
from decimal import Decimal

import pytest
from mcp_shop.domain.money import decimal_to_cents, parse_argentine_amount
from mcp_shop.domain.receipts import (
    RawReceipt,
    normalize_cuit,
    parse_local_datetime,
    parse_receipt,
)


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("$ 2.166,35", 216635),
        ("$2.166,35", 216635),
        ("2166,35", 216635),
        ("$ 1.000", 100000),
        ("$ 5,5", 550),
        ("$\u00a0300,00", 30000),
        ("ARS 1.234.567,89", 123456789),
        ("$ 3", 300),
    ],
)
def test_argentine_amounts_parse_to_cents(text, cents):
    assert parse_argentine_amount(text) == cents


@pytest.mark.parametrize("text", ["", "$", "2,166.35", "12,345", "1.23", "$ 0,00", "abc", "-5"])
def test_ambiguous_or_invalid_amounts_are_rejected(text):
    assert parse_argentine_amount(text) is None


@pytest.mark.parametrize(
    ("value", "cents"), [("2166.35", 216635), (2166.35, 216635), (5, 500), (Decimal("0.1"), 10)]
)
def test_provider_decimals_convert_exactly(value, cents):
    assert decimal_to_cents(value) == cents


def test_sub_cent_provider_amount_is_an_error():
    with pytest.raises(ValueError):
        decimal_to_cents("1.005")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("23/11/2026 12:14", datetime(2026, 11, 23, 15, 14, tzinfo=UTC)),
        ("23/11/2026 - 12:14:30 hs", datetime(2026, 11, 23, 15, 14, 30, tzinfo=UTC)),
        ("23-11-26 23:59", datetime(2026, 11, 24, 2, 59, tzinfo=UTC)),
        (
            "Lunes, 23 de noviembre de 2026 a las 12:14 hs",
            datetime(2026, 11, 23, 15, 14, tzinfo=UTC),
        ),
        ("23 nov. 2026, 9:05 p. m.", datetime(2026, 11, 24, 0, 5, tzinfo=UTC)),
        ("23 Sep 2026 12:00 a.m.", datetime(2026, 9, 23, 3, 0, tzinfo=UTC)),
    ],
)
def test_local_receipt_time_is_converted_to_utc(text, expected):
    assert parse_local_datetime(text) == expected


@pytest.mark.parametrize("text", ["23/11/2026", "12:14", "31/02/2026 10:00", "yesterday"])
def test_incomplete_or_invalid_times_are_rejected(text):
    assert parse_local_datetime(text) is None


def test_cuit_is_normalized_to_eleven_digits():
    assert normalize_cuit("20-00000000-1") == "20000000001"
    assert normalize_cuit("2000") is None
    assert normalize_cuit(None) is None


def test_parse_receipt_combines_all_fields():
    parsed = parse_receipt(
        RawReceipt(
            is_receipt=True,
            coelsa_id="synth coelsa 01",
            amount_text="$ 5,00",
            datetime_local_text="23/11/2026 12:14",
            origin_cuit="20-00000000-1",
        )
    )
    assert parsed.coelsa_id == "SYNTHCOELSA01"
    assert parsed.amount_cents == 500
    assert parsed.sent_at == datetime(2026, 11, 23, 15, 14, tzinfo=UTC)
    assert parsed.origin_cuit == "20000000001"
