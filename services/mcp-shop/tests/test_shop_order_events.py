"""Outbox for order_created: commit first, publish with retries, drain on later calls."""

import pytest
from shop_fakes import RECEIPT_REF, World, caller, order

DOG = [{"animal": "dog", "qty": 1}]


async def test_event_is_published_and_marked_after_commit(world: World):
    outcome = await world.shop.create_order(caller(), DOG)
    assert [o.order_id for o in world.publisher.orders] == [outcome.order_id]
    assert world.repository.pending_events == set()
    assert world.sleeps == []


async def test_publish_retries_with_backoff(world: World):
    world.publisher.failures_left = 2
    await world.shop.create_order(caller(), DOG)
    assert world.sleeps == [0.2, 0.4]
    assert len(world.publisher.orders) == 1
    assert world.repository.pending_events == set()


async def test_order_is_created_even_when_every_attempt_fails(world: World):
    world.publisher.failures_left = 3
    outcome = await world.shop.create_order(caller(), DOG)
    assert outcome.status == "created"
    assert world.publisher.orders == []
    assert world.repository.pending_events == {outcome.order_id}


@pytest.mark.parametrize(
    "call",
    [
        lambda shop: shop.get_balance(caller()),
        lambda shop: shop.get_order_status(caller(), "ord_missing"),
        lambda shop: shop.verify_receipt(caller(receipt=RECEIPT_REF)),
        lambda shop: shop.create_order(caller(), DOG),
        # A stale sign-in still drains the outbox: re-publishing reveals nothing.
        lambda shop: shop.get_balance(caller(auth_fresh=False)),
    ],
)
async def test_any_later_call_republishes_pending_orders(world: World, call):
    world.publisher.failures_left = 3
    lost = await world.shop.create_order(caller(), DOG)

    await call(world.shop)

    assert world.publisher.orders[0].order_id == lost.order_id
    assert lost.order_id not in world.repository.pending_events


async def test_outbox_is_per_customer(world: World):
    world.publisher.failures_left = 3
    await world.shop.create_order(caller(), DOG)
    await world.shop.get_balance(caller(customer_id="cust-synthetic-2"))
    await world.shop.get_balance(caller(customer_id=None))
    assert world.publisher.orders == []


async def test_drain_stops_while_the_publisher_is_down(world: World):
    for order_id, minutes_ago in (("ord_a", 30), ("ord_b", 20)):
        world.repository.add_order(order(order_id, 100, minutes_ago=minutes_ago))
        world.repository.pending_events.add(order_id)
    world.publisher.failures_left = 3

    await world.shop.get_order_status(caller(), "ord_a")

    assert world.repository.pending_events == {"ord_a", "ord_b"}
    assert world.sleeps == [0.2, 0.4]  # one order's retries, not both

    await world.shop.get_order_status(caller(), "ord_a")
    assert [o.order_id for o in world.publisher.orders] == ["ord_a", "ord_b"]
    assert world.repository.pending_events == set()
