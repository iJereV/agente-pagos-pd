import pytest
from mcp_shop.domain.catalog import Animal
from mcp_shop.domain.matching import ReviewReason
from mcp_shop.domain.orders import OrderStatus
from mcp_shop.domain.receipts import RawReceipt
from shop_fakes import CUSTOMER, RECEIPT_REF, WA_ID, World, caller, order, transfer

COELSA = "SYNTHCOELSA00000000000001"


def bank_receipt(coelsa_id: str | None = COELSA, amount_text: str = "$ 5,00") -> RawReceipt:
    return RawReceipt(
        is_receipt=True,
        coelsa_id=coelsa_id,
        amount_text=amount_text,
        datetime_local_text="23/11/2026 14:48",  # 17:48 UTC, ten minutes before NOW
        origin_cuit="20-00000000-1",
        destination_cvu="0000000000000000000000",
        bank_name="Synthetic Bank",
    )


# --- access rules -----------------------------------------------------------


async def test_unlinked_caller_gets_not_linked_everywhere(world: World):
    anonymous = caller(customer_id=None)
    shop = world.shop
    assert (await shop.get_balance(anonymous)).status == "not_linked"
    assert (
        await shop.create_order(anonymous, [{"animal": "dog", "qty": 1}])
    ).status == "not_linked"
    assert (await shop.verify_receipt(anonymous)).status == "not_linked"
    assert (await shop.get_order_status(anonymous, "ord_x")).status == "not_linked"


async def test_stale_sign_in_requires_auth_for_balance_and_orders(world: World):
    stale = caller(auth_fresh=False)
    assert (await world.shop.get_balance(stale)).status == "auth_required"
    assert (await world.shop.create_order(stale, [{"animal": "dog", "qty": 1}])).status == (
        "auth_required"
    )
    assert world.repository.orders == {}


async def test_receipt_verification_does_not_need_a_fresh_sign_in(world: World):
    stale = caller(auth_fresh=False, receipt=RECEIPT_REF)
    world.receipt(bank_receipt())
    world.transfers.add(transfer(e2e_id=COELSA))
    assert (await world.shop.verify_receipt(stale)).status == "credited"


# --- create_order -----------------------------------------------------------


async def test_create_order_stores_and_publishes(world: World):
    outcome = await world.shop.create_order(
        caller(), [{"animal": "dog", "qty": 2}, {"animal": "capybara", "qty": 1}]
    )
    assert outcome.model_dump() == {
        "status": "created",
        "order_id": "ord_test1",
        "total_cents": 700,
        "credit_used_cents": 0,
    }
    stored = world.repository.orders["ord_test1"]
    assert stored.customer_id == CUSTOMER and stored.wa_id == WA_ID
    assert [(line.animal, line.qty) for line in stored.lines] == [
        (Animal.DOG, 2),
        (Animal.CAPYBARA, 1),
    ]
    assert world.publisher.orders == [stored]


async def test_create_order_over_the_limit_is_refused(world: World):
    world.repository.add_order(order("ord_old", 800))
    outcome = await world.shop.create_order(caller(), [{"animal": "penguin", "qty": 1}])
    assert outcome.model_dump() == {"status": "credit_limit", "available_credit_cents": 200}
    assert world.publisher.orders == []


async def test_create_order_uses_credit_balance_first(world: World):
    world.repository.credit[CUSTOMER] = 250
    outcome = await world.shop.create_order(caller(), [{"animal": "penguin", "qty": 1}])
    assert outcome.credit_used_cents == 250
    assert world.repository.credit[CUSTOMER] == 0
    assert world.repository.orders["ord_test1"].status is OrderStatus.PARTIALLY_PAID


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"animal": "cat", "qty": 1}],
        [{"animal": "dog", "qty": 0}],
        [{"animal": "dog", "qty": 6}],
        [{"animal": "dog", "qty": "2"}],
        [{"animal": "dog"}],
        [{"animal": "dog", "qty": 1, "price": 0}],
        "dog",
    ],
)
async def test_invalid_items_are_rejected_without_writing(world: World, items):
    assert (await world.shop.create_order(caller(), items)).status == "invalid_items"
    assert world.repository.orders == {}


# --- get_balance and get_order_status --------------------------------------


async def test_balance_lists_unpaid_orders_oldest_first(world: World):
    world.repository.add_order(order("ord_b", 500, minutes_ago=5))
    world.repository.add_order(order("ord_a", 300, paid=100, minutes_ago=50))
    world.repository.add_order(order("ord_paid", 100, paid=100, minutes_ago=90))
    balance = await world.shop.get_balance(caller())
    assert balance.debt_cents == 700
    assert balance.credit_balance_cents == 0
    assert balance.available_credit_cents == 300
    assert [o.order_id for o in balance.unpaid_orders] == ["ord_a", "ord_b"]


async def test_order_status_only_for_the_owner(world: World):
    world.repository.add_order(order("ord_a", 500, paid=200))
    mine = await world.shop.get_order_status(caller(), "ord_a")
    assert mine.model_dump() == {
        "status": "ok",
        "order_status": "partially_paid",
        "total_cents": 500,
        "paid_cents": 200,
    }
    someone_else = caller(customer_id="cust-synthetic-2")
    assert (await world.shop.get_order_status(someone_else, "ord_a")).status == "not_found"
    assert (await world.shop.get_order_status(caller(), "ord_missing")).status == "not_found"


# --- verify_receipt ---------------------------------------------------------


async def test_no_receipt_without_a_reference_or_stored_file(world: World):
    assert (await world.shop.verify_receipt(caller())).status == "no_receipt"
    assert (await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))).status == "no_receipt"
    outside = caller(receipt="orders/ord_x/1.png")
    assert (await world.shop.verify_receipt(outside)).status == "no_receipt"


async def test_not_a_receipt(world: World):
    world.receipt(RawReceipt(is_receipt=False))
    assert (await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))).status == "not_a_receipt"


async def test_credit_allocates_oldest_first_with_credit_remainder(world: World):
    world.repository.add_order(order("ord_new", 300, minutes_ago=20))
    world.repository.add_order(order("ord_old", 100, minutes_ago=200))
    world.receipt(bank_receipt())
    world.transfers.add(transfer(e2e_id=COELSA, amount=500))

    outcome = await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))

    assert outcome.model_dump() == {
        "status": "credited",
        "amount_cents": 500,
        "allocations": [
            {"order_id": "ord_old", "amount_cents": 100},
            {"order_id": "ord_new", "amount_cents": 300},
        ],
        "credit_balance_cents": 100,
        "debt_cents": 0,
    }
    assert world.repository.orders["ord_old"].status is OrderStatus.PAID
    assert world.repository.credit[CUSTOMER] == 100
    payment = world.repository.payments[COELSA]
    assert payment.match_method == "coelsa_id" and payment.receipt_ref == RECEIPT_REF


async def test_credited_amount_is_the_provider_amount(world: World):
    world.receipt(bank_receipt(coelsa_id=None, amount_text="$ 5,00"))
    world.transfers.add(transfer(e2e_id=None, amount=500, payer_cuit=None))
    outcome = await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))
    assert outcome.status == "credited" and outcome.amount_cents == 500
    assert world.repository.payments["simulated-sim-1"].match_method == "amount_cuit_window"


async def test_same_transfer_cannot_be_used_twice(world: World):
    world.receipt(bank_receipt())
    world.transfers.add(transfer(e2e_id=COELSA))
    assert (await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))).status == "credited"
    other_customer = caller(customer_id="cust-synthetic-2", receipt=RECEIPT_REF)
    assert (await world.shop.verify_receipt(other_customer)).status == "already_used"
    assert world.repository.credit.get("cust-synthetic-2", 0) == 0


async def test_near_coelsa_id_goes_to_manual_review(world: World):
    world.receipt(bank_receipt(coelsa_id="SYNTHC0ELSA00000000000001"))
    world.transfers.add(transfer(e2e_id=COELSA))

    outcome = await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))

    assert outcome.status == "manual_review"
    assert world.repository.payments == {}
    [review] = world.repository.reviews.values()
    assert review.reason is ReviewReason.NEAR_COELSA_ID
    assert review.customer_id == CUSTOMER and review.receipt_ref == RECEIPT_REF
    assert review.extracted["coelsa_id"] == "SYNTHC0ELSA00000000000001"
    assert [c.e2e_id for c in review.candidates] == [COELSA]


async def test_repeated_review_does_not_duplicate(world: World):
    world.receipt(bank_receipt(amount_text="illegible"))
    await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))
    await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))
    assert len(world.repository.reviews) == 1


async def test_not_found_yet_when_the_transfer_has_not_arrived(world: World):
    world.receipt(bank_receipt())
    assert (await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))).status == "not_found_yet"
