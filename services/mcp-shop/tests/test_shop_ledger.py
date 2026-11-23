import pytest
from mcp_shop.domain.allocation import Allocation, allocate
from mcp_shop.domain.catalog import Animal, OrderLine, order_total_cents
from mcp_shop.domain.ledger import CreditLimitExceeded, Ledger
from mcp_shop.domain.orders import OrderStatus
from shop_fakes import CUSTOMER, NOW, WA_ID, order

LIMIT = 1000


def place(ledger: Ledger, *lines: OrderLine):
    return ledger.place_order(
        order_id="ord_new", wa_id=WA_ID, lines=lines, created_at=NOW, credit_limit_cents=LIMIT
    )


def test_catalog_prices_in_cents():
    lines = (OrderLine(Animal.DOG, 2), OrderLine(Animal.PENGUIN, 1), OrderLine(Animal.CAPYBARA, 1))
    assert order_total_cents(lines) == 200 + 300 + 500


@pytest.mark.parametrize("qty", [0, 6, -1])
def test_quantity_outside_one_to_five_is_rejected(qty):
    with pytest.raises(ValueError):
        OrderLine(Animal.DOG, qty)


def test_order_up_to_the_limit_is_accepted():
    ledger = Ledger(CUSTOMER, 0, [order("ord_a", 500)])
    placed = place(ledger, OrderLine(Animal.CAPYBARA, 1))
    assert placed.order.total_cents == 500
    assert ledger.debt_cents == 1000
    assert ledger.available_credit_cents(LIMIT) == 0


def test_order_over_the_limit_reports_available_credit():
    ledger = Ledger(CUSTOMER, 0, [order("ord_a", 800)])
    with pytest.raises(CreditLimitExceeded) as exceeded:
        place(ledger, OrderLine(Animal.PENGUIN, 1))
    assert exceeded.value.available_credit_cents == 200
    assert len(ledger.unpaid_orders) == 1


def test_credit_balance_counts_towards_the_limit_and_is_consumed_first():
    ledger = Ledger(CUSTOMER, 300, [])
    placed = place(ledger, OrderLine(Animal.CAPYBARA, 2), OrderLine(Animal.PENGUIN, 1))
    assert placed.order.total_cents == 1300
    assert placed.credit_used_cents == 300
    assert placed.order.paid_cents == 300
    assert placed.order.status is OrderStatus.PARTIALLY_PAID
    assert ledger.credit_balance_cents == 0
    assert ledger.debt_cents == 1000


def test_order_fully_covered_by_credit_is_paid_and_adds_no_debt():
    ledger = Ledger(CUSTOMER, 500, [])
    placed = place(ledger, OrderLine(Animal.DOG, 2))
    assert placed.order.status is OrderStatus.PAID
    assert ledger.credit_balance_cents == 300
    assert ledger.unpaid_orders == []


def test_allocation_pays_oldest_first_and_keeps_the_remainder():
    newer = order("ord_new", 500, minutes_ago=10)
    older = order("ord_old", 300, paid=100, minutes_ago=90)
    result = allocate(800, [newer, older])
    assert result.allocations == (Allocation("ord_old", 200), Allocation("ord_new", 500))
    assert result.remainder_cents == 100
    assert older.status is OrderStatus.PAID
    assert newer.status is OrderStatus.PAID


def test_partial_payment_leaves_the_order_partially_paid():
    first = order("ord_a", 500, minutes_ago=30)
    second = order("ord_b", 500, minutes_ago=5)
    result = allocate(200, [second, first])
    assert result.allocations == (Allocation("ord_a", 200),)
    assert first.status is OrderStatus.PARTIALLY_PAID
    assert second.status is OrderStatus.UNPAID


def test_payment_with_no_debt_becomes_credit_balance():
    ledger = Ledger(CUSTOMER, 0, [])
    result = ledger.apply_payment(400)
    assert result.allocations == ()
    assert ledger.credit_balance_cents == 400


def test_order_cannot_be_overpaid():
    with pytest.raises(ValueError):
        order("ord_a", 100).pay(200)
