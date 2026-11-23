from types import SimpleNamespace

import pytest
from shop_agent.tools import format_pesos, get_catalog, request_sign_in


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
