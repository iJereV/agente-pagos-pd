import pytest
from mcp_shop.domain.catalog import Animal
from mcp_shop.domain.ledger import Movement, MovementKind
from mcp_shop.domain.matching import ReviewReason
from mcp_shop.domain.orders import OrderStatus
from mcp_shop.domain.receipts import RawReceipt
from shop_fakes import CUSTOMER, NOW, RECEIPT_REF, WA_ID, World, caller, order, transfer

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


def welcome_movement() -> Movement:
    return Movement(f"welcome:{CUSTOMER}", CUSTOMER, MovementKind.WELCOME_CREDIT, 1000, 1000, NOW)


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
    assert world.repository.movements == {}


async def test_receipt_verification_does_not_need_a_fresh_sign_in(world: World):
    stale = caller(auth_fresh=False, receipt=RECEIPT_REF)
    world.receipt(bank_receipt())
    world.transfers.add(transfer(e2e_id=COELSA))
    assert (await world.shop.verify_receipt(stale)).status == "credited"


# --- create_order -----------------------------------------------------------


async def test_first_order_is_paid_from_the_welcome_credit(world: World):
    outcome = await world.shop.create_order(
        caller(), [{"animal": "dog", "qty": 2}, {"animal": "capybara", "qty": 1}]
    )
    assert outcome.model_dump() == {
        "status": "created",
        "order_id": "ord_test1",
        "total_cents": 700,
        "balance_cents": 300,
    }
    stored = world.repository.orders["ord_test1"]
    assert stored.customer_id == CUSTOMER and stored.wa_id == WA_ID
    assert stored.status is OrderStatus.PAID
    assert [(line.animal, line.qty) for line in stored.lines] == [
        (Animal.DOG, 2),
        (Animal.CAPYBARA, 1),
    ]
    assert world.publisher.orders == [stored]
    assert world.repository.balances[CUSTOMER] == 300
    assert world.repository.movement_kinds(CUSTOMER) == ["welcome_credit", "order"]


async def test_orders_debit_until_the_balance_runs_out(world: World):
    capybara = [{"animal": "capybara", "qty": 1}]
    assert (await world.shop.create_order(caller(), capybara)).balance_cents == 500
    assert (await world.shop.create_order(caller(), capybara)).balance_cents == 0

    outcome = await world.shop.create_order(caller(), [{"animal": "dog", "qty": 1}])

    assert outcome.model_dump() == {
        "status": "insufficient_balance",
        "balance_cents": 0,
        "total_cents": 100,
        "payment_needed_cents": 100,
    }
    assert world.repository.balances[CUSTOMER] == 0
    assert len(world.repository.orders) == 2


async def test_order_over_the_balance_is_refused_without_writing(world: World):
    outcome = await world.shop.create_order(
        caller(), [{"animal": "capybara", "qty": 2}, {"animal": "penguin", "qty": 1}]
    )
    assert outcome.model_dump() == {
        "status": "insufficient_balance",
        "balance_cents": 1000,
        "total_cents": 1300,
        "payment_needed_cents": 300,
    }
    assert world.repository.orders == {}
    assert world.repository.movements == {}
    assert world.publisher.orders == []
    # The welcome credit is still granted on the next successful operation.
    assert (await world.shop.get_balance(caller())).balance_cents == 1000


async def test_welcome_credit_is_never_granted_twice(world: World):
    await world.shop.get_balance(caller())
    await world.shop.get_balance(caller())
    await world.shop.create_order(caller(), [{"animal": "dog", "qty": 1}])
    assert world.repository.movement_kinds(CUSTOMER) == ["welcome_credit", "order"]
    assert world.repository.balances[CUSTOMER] == 900


async def test_existing_balance_without_the_welcome_movement_gets_it_added(world: World):
    world.repository.balances[CUSTOMER] = 250
    assert (await world.shop.get_balance(caller())).balance_cents == 1250


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


async def test_new_customer_balance_is_the_welcome_credit(world: World):
    balance = await world.shop.get_balance(caller())
    assert balance.model_dump() == {"status": "ok", "balance_cents": 1000}
    [welcome] = world.repository.movements.values()
    assert welcome.movement_id == f"welcome:{CUSTOMER}" and welcome.created_at == NOW


async def test_legacy_unpaid_orders_do_not_change_the_balance(world: World):
    world.repository.add_order(order("ord_old", 500, paid=0))
    assert (await world.shop.get_balance(caller())).balance_cents == 1000


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


async def test_verified_transfer_is_added_to_the_balance(world: World):
    world.repository.balances[CUSTOMER] = 50
    world.repository.movements[f"welcome:{CUSTOMER}"] = welcome_movement()
    world.receipt(bank_receipt())
    world.transfers.add(transfer(e2e_id=COELSA, amount=500))

    outcome = await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))

    assert outcome.model_dump() == {"status": "credited", "amount_cents": 500, "balance_cents": 550}
    assert world.repository.balances[CUSTOMER] == 550
    payment = world.repository.payments[COELSA]
    assert payment.match_method == "coelsa_id" and payment.receipt_ref == RECEIPT_REF
    assert payment.balance_cents == 550
    assert world.repository.movements[f"payment:{COELSA}"].amount_cents == 500


async def test_first_transfer_of_a_new_customer_also_grants_the_welcome_credit(world: World):
    world.receipt(bank_receipt())
    world.transfers.add(transfer(e2e_id=COELSA, amount=500))
    outcome = await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))
    assert outcome.balance_cents == 1500
    assert world.repository.movement_kinds(CUSTOMER) == ["welcome_credit", "payment"]


async def test_payment_unblocks_an_order_refused_for_insufficient_balance(world: World):
    big = [{"animal": "capybara", "qty": 3}]
    refused = await world.shop.create_order(caller(), big)
    assert refused.payment_needed_cents == 500
    world.receipt(bank_receipt())
    world.transfers.add(transfer(e2e_id=COELSA, amount=500))
    assert (await world.shop.verify_receipt(caller(receipt=RECEIPT_REF))).balance_cents == 1500

    placed = await world.shop.create_order(caller(), big)

    assert placed.status == "created" and placed.balance_cents == 0


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
    assert world.repository.balances.get("cust-synthetic-2", 0) == 0


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
