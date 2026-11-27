import pytest
from mcp_shop.domain.catalog import Animal, OrderLine, order_total_cents
from mcp_shop.domain.ledger import InsufficientBalance, Ledger, MovementKind
from mcp_shop.domain.orders import OrderStatus
from shop_fakes import CUSTOMER, NOW, WA_ID, order

WELCOME = 1000


def place(ledger: Ledger, *lines: OrderLine):
    return ledger.place_order(order_id="ord_new", wa_id=WA_ID, lines=lines, created_at=NOW)


def test_catalog_prices_in_cents():
    lines = (OrderLine(Animal.DOG, 2), OrderLine(Animal.PENGUIN, 1), OrderLine(Animal.CAPYBARA, 1))
    assert order_total_cents(lines) == 200 + 300 + 500


@pytest.mark.parametrize("qty", [0, 6, -1])
def test_quantity_outside_one_to_five_is_rejected(qty):
    with pytest.raises(ValueError):
        OrderLine(Animal.DOG, qty)


def test_welcome_credit_is_granted_once_as_a_movement():
    ledger = Ledger(CUSTOMER, 0, welcome_credit_granted=False)
    ledger.grant_welcome_credit(WELCOME, NOW)
    ledger.grant_welcome_credit(WELCOME, NOW)
    assert ledger.balance_cents == 1000
    [movement] = ledger.movements
    assert movement.movement_id == f"welcome:{CUSTOMER}"
    assert movement.kind is MovementKind.WELCOME_CREDIT
    assert (movement.amount_cents, movement.balance_after_cents) == (1000, 1000)


def test_welcome_credit_is_not_granted_again_to_a_ledger_that_had_it():
    ledger = Ledger(CUSTOMER, 300, welcome_credit_granted=True)
    ledger.grant_welcome_credit(WELCOME, NOW)
    assert ledger.balance_cents == 300
    assert ledger.movements == []


def test_zero_welcome_credit_grants_nothing():
    ledger = Ledger(CUSTOMER, 0, welcome_credit_granted=False)
    ledger.grant_welcome_credit(0, NOW)
    assert ledger.balance_cents == 0
    assert ledger.movements == []
    assert ledger.welcome_credit_granted is False


def test_order_up_to_the_balance_is_paid_and_debited():
    ledger = Ledger(CUSTOMER, 1000, welcome_credit_granted=True)
    placed = place(ledger, OrderLine(Animal.CAPYBARA, 2))
    assert placed.order.total_cents == 1000
    assert placed.order.status is OrderStatus.PAID
    assert placed.balance_cents == 0
    assert ledger.balance_cents == 0
    [movement] = ledger.movements
    assert movement.movement_id == "order:ord_new"
    assert (movement.kind, movement.amount_cents) == (MovementKind.ORDER, -1000)
    assert movement.reference == "ord_new"


def test_order_over_the_balance_is_refused_and_says_what_is_missing():
    ledger = Ledger(CUSTOMER, 200, welcome_credit_granted=True)
    with pytest.raises(InsufficientBalance) as short:
        place(ledger, OrderLine(Animal.CAPYBARA, 1))
    assert (short.value.balance_cents, short.value.total_cents) == (200, 500)
    assert short.value.payment_needed_cents == 300
    assert ledger.balance_cents == 200
    assert ledger.movements == []


def test_payment_adds_to_the_balance():
    ledger = Ledger(CUSTOMER, 150, welcome_credit_granted=True)
    ledger.credit_payment("SYNTHCOELSA00000000000001", 400, NOW)
    assert ledger.balance_cents == 550
    [movement] = ledger.movements
    assert movement.movement_id == "payment:SYNTHCOELSA00000000000001"
    assert (movement.kind, movement.amount_cents) == (MovementKind.PAYMENT, 400)
    assert movement.balance_after_cents == 550


def test_payment_must_be_positive():
    with pytest.raises(ValueError):
        Ledger(CUSTOMER, 0, welcome_credit_granted=True).credit_payment("sim-1", 0, NOW)


def test_order_status_reads_legacy_unpaid_orders():
    assert order("ord_a", 500).status is OrderStatus.PAID
    assert order("ord_b", 500, paid=200).status is OrderStatus.PARTIALLY_PAID
    assert order("ord_c", 500, paid=0).status is OrderStatus.UNPAID
