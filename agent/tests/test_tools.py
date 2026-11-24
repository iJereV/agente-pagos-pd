from types import SimpleNamespace

import pytest
from shop_agent.tools import format_pesos, get_catalog, get_payment_details, request_sign_in


def test_catalog_matches_contract_prices():
    catalog = get_catalog()

    assert catalog["currency"] == "ARS"
    assert catalog["items"] == [
        {"animal": "dog", "price_cents": 100, "price": "$1"},
        {"animal": "penguin", "price_cents": 300, "price": "$3"},
        {"animal": "capybara", "price_cents": 500, "price": "$5"},
    ]


@pytest.mark.parametrize(
    ("cents", "text"), [(0, "$0"), (100, "$1"), (150, "$1,50"), (1005, "$10,05")]
)
def test_format_pesos(cents, text):
    assert format_pesos(cents) == text


def test_request_sign_in_sets_session_state():
    context = SimpleNamespace(state={})

    result = request_sign_in(context)

    assert result == {"requested": True}
    assert context.state == {"sign_in_requested": True}


def test_payment_details_repeat_only_configured_values(monkeypatch):
    monkeypatch.setenv("PAYMENT_ALIAS", "shop.alias.test")
    monkeypatch.setenv("PAYMENT_HOLDER", "TEST HOLDER")
    monkeypatch.delenv("PAYMENT_CVU", raising=False)

    assert get_payment_details() == {
        "available": True,
        "alias": "shop.alias.test",
        "holder": "TEST HOLDER",
    }


def test_payment_details_unavailable_without_alias_or_cvu(monkeypatch):
    for name in ("PAYMENT_ALIAS", "PAYMENT_CVU"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PAYMENT_HOLDER", "TEST HOLDER")

    assert get_payment_details() == {"available": False}
