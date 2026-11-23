from datetime import timedelta

from main_worker.domain.models import OrderReady
from main_worker_testkit import (
    CUSTOMER_ID,
    WA_ID,
    World,
    text_message,
)

ORDER = OrderReady(
    order_id="ord_TEST1",
    wa_id=WA_ID,
    customer_id=CUSTOMER_ID,
    images=("orders/ord_TEST1/1.png", "orders/ord_TEST1/2.png"),
)


def store_images(world: World) -> None:
    for n, path in enumerate(ORDER.images, start=1):
        world.media.objects[path] = (f"png-{n}".encode(), "image/png")


async def open_window(world: World) -> None:
    world.link(timedelta(hours=1))
    await world.inbound.handle(text_message("quiero dos perritos"))
    world.whatsapp.sent.clear()


async def test_inside_window_sends_agent_text_then_images(world: World) -> None:
    await open_window(world)
    store_images(world)
    world.agent.replies = ["¡Acá están tus perritos!"]

    await world.deliveries.handle_order_ready(ORDER)

    assert world.agent.turns[-1][1] == (
        'SYSTEM_EVENT {"event":"order_ready","order_id":"ord_TEST1","image_count":2}'
    )
    assert world.whatsapp.sent == [
        ("text", WA_ID, "¡Acá están tus perritos!"),
        ("image", WA_ID, "uploaded-1"),
        ("image", WA_ID, "uploaded-2"),
    ]
    assert world.whatsapp.uploads == [("1.png", b"png-1"), ("2.png", b"png-2")]
    assert world.store.deliveries["ord_TEST1"]["status"] == "delivered"


async def test_outside_window_sends_template_and_waits(world: World) -> None:
    await open_window(world)
    world.clock.advance(timedelta(hours=25))
    turns_before = len(world.agent.turns)

    await world.deliveries.handle_order_ready(ORDER)

    assert world.whatsapp.sent == [("template", WA_ID, ("hello_world", "en_US"))]
    assert len(world.agent.turns) == turns_before
    assert world.store.deliveries["ord_TEST1"]["status"] == "awaiting_window"


async def test_never_contacted_number_gets_the_template(world: World) -> None:
    await world.deliveries.handle_order_ready(ORDER)

    assert [kind for kind, _, _ in world.whatsapp.sent] == ["template"]


async def test_order_ready_is_idempotent(world: World) -> None:
    await open_window(world)
    store_images(world)

    await world.deliveries.handle_order_ready(ORDER)
    await world.deliveries.handle_order_ready(ORDER)

    assert [kind for kind, _, _ in world.whatsapp.sent] == ["text", "image", "image"]


async def test_awaiting_delivery_is_sent_after_the_customer_writes_again(world: World) -> None:
    store_images(world)
    await world.deliveries.handle_order_ready(ORDER)
    world.agent.replies = ["¡Hola de nuevo!", "Tus imágenes:"]

    await world.inbound.handle(text_message("hola", wamid="wamid.BACK"))

    assert [(kind, body) for kind, _, body in world.whatsapp.sent] == [
        ("template", ("hello_world", "en_US")),
        ("text", "¡Hola de nuevo!"),
        ("text", "Tus imágenes:"),
        ("image", "uploaded-1"),
        ("image", "uploaded-2"),
    ]
    assert world.store.deliveries["ord_TEST1"]["status"] == "delivered"


async def test_failed_pending_delivery_does_not_fail_the_message(world: World) -> None:
    await world.deliveries.handle_order_ready(ORDER)  # Images missing in the bucket.

    await world.inbound.handle(text_message("hola", wamid="wamid.BACK"))

    assert world.store.deliveries["ord_TEST1"]["status"] == "awaiting_window"
    assert "wamid.BACK" in world.store.processed
