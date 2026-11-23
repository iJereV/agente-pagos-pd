from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from main_worker.domain.models import MediaFile
from main_worker_testkit import (
    CUSTOMER_ID,
    WA_ID,
    World,
    text_message,
)
from shared.tokens import verify_link_token, verify_turn_token


def image_message(wamid: str = "wamid.IMG1", caption: str | None = "ya pagué") -> dict:
    return text_message(caption, wamid) | {
        "message_type": "image",
        "media_id": "MEDIA_1",
        "mime_type": "image/jpeg",
    }


async def test_duplicate_message_is_processed_once(world: World) -> None:
    await world.inbound.handle(text_message())
    await world.inbound.handle(text_message())

    assert len(world.agent.turns) == 1
    assert world.whatsapp.texts() == ["ok"]


async def test_failed_message_releases_its_claim_for_the_retry(world: World) -> None:
    async def failing_turn(*_: object) -> str:
        raise RuntimeError("agent runtime unavailable")

    world.agent.run_turn = failing_turn
    with pytest.raises(RuntimeError):
        await world.inbound.handle(text_message())

    assert world.store.processed == {}


async def test_unlinked_number_gets_anonymous_state_and_token(world: World) -> None:
    await world.inbound.handle(text_message("quiero dos perritos"))

    state = world.agent.state_at_turn[0]
    assert state | {"turn_token": "-"} == {
        "wa_id": WA_ID,
        "customer_id": None,
        "is_linked": False,
        "auth_fresh": False,
        "turn_token": "-",
    }
    claims = verify_turn_token(state["turn_token"])
    assert (claims.customer_id, claims.wa_id, claims.auth_fresh) == (None, WA_ID, False)
    assert world.agent.turns[0][1] == "quiero dos perritos"


@pytest.mark.parametrize(
    ("signed_in_ago", "fresh"),
    [(timedelta(hours=2), True), (timedelta(hours=30), False), (None, False)],
)
async def test_linked_number_freshness_follows_last_sign_in(
    world: World, signed_in_ago: timedelta | None, fresh: bool
) -> None:
    world.link(signed_in_ago)

    await world.inbound.handle(text_message())

    state = world.agent.state_at_turn[0]
    assert (state["customer_id"], state["is_linked"], state["auth_fresh"]) == (
        CUSTOMER_ID,
        True,
        fresh,
    )
    assert verify_turn_token(state["turn_token"]).customer_id == CUSTOMER_ID


async def test_session_is_reused_until_idle_then_rotated(world: World) -> None:
    await world.inbound.handle(text_message(wamid="wamid.A"))
    world.clock.advance(timedelta(hours=23))
    await world.inbound.handle(text_message(wamid="wamid.B"))
    world.clock.advance(timedelta(hours=25))
    await world.inbound.handle(text_message(wamid="wamid.C"))

    assert [session for session, _ in world.agent.turns] == ["session-1", "session-1", "session-2"]
    pointer = world.store.sessions[WA_ID]
    assert pointer.last_activity == world.clock() == pointer.last_inbound_at


async def test_vanished_session_is_recreated(world: World) -> None:
    await world.inbound.handle(text_message(wamid="wamid.A"))
    world.agent.sessions.clear()

    await world.inbound.handle(text_message(wamid="wamid.B"))

    assert world.store.sessions[WA_ID].session_id == "session-1"
    assert len(world.agent.turns) == 2


async def test_receipt_is_stored_and_referenced_by_the_turn_token(world: World) -> None:
    world.link(timedelta(hours=1))
    world.whatsapp.media["MEDIA_1"] = MediaFile(b"fake-jpeg", "image/jpeg")

    await world.inbound.handle(image_message())
    await world.inbound.handle(text_message("ya está", wamid="wamid.TXT2"))

    path = f"receipts/{CUSTOMER_ID}/wamid.IMG1.jpg"
    assert world.media.objects[path] == (b"fake-jpeg", "image/jpeg")
    assert world.agent.turns[0][1] == "[image received] ya pagué"
    tokens = [verify_turn_token(s["turn_token"]) for s in world.agent.state_at_turn]
    assert [t.last_receipt_ref for t in tokens] == [path, path]


async def test_unlinked_receipt_is_stored_under_the_wa_id(world: World) -> None:
    world.whatsapp.media["MEDIA_1"] = MediaFile(b"fake-jpeg", "image/jpeg")

    await world.inbound.handle(image_message(caption=None))

    assert f"receipts/{WA_ID}/wamid.IMG1.jpg" in world.media.objects
    assert world.agent.turns[0][1] == "[image received]"


async def test_receipt_reference_does_not_survive_rotation(world: World) -> None:
    world.whatsapp.media["MEDIA_1"] = MediaFile(b"fake-jpeg", "image/jpeg")
    await world.inbound.handle(image_message())
    world.clock.advance(timedelta(hours=30))

    await world.inbound.handle(text_message(wamid="wamid.LATER"))

    assert verify_turn_token(world.agent.state_at_turn[-1]["turn_token"]).last_receipt_ref is None


async def test_sign_in_placeholder_is_replaced_with_a_link(world: World) -> None:
    world.agent.request_sign_in = True
    world.agent.replies = ["Ingresá acá: {{SIGN_IN_LINK}} y volvé."]

    await world.inbound.handle(text_message("quiero comprar"))

    [reply] = world.whatsapp.texts()
    url = reply.removeprefix("Ingresá acá: ").removesuffix(" y volvé.")
    assert url.startswith("https://link.example.test/link?t=")
    claims = verify_link_token(parse_qs(urlparse(url).query)["t"][0])
    assert (claims.wa_id, claims.purpose) == (WA_ID, "link")
    assert [t["purpose"] for t in world.store.link_tokens.values()] == ["link"]
    assert world.agent.sessions["session-1"]["sign_in_requested"] is False


async def test_sign_in_link_is_appended_when_placeholder_is_missing(world: World) -> None:
    world.link(timedelta(hours=48))
    world.agent.request_sign_in = True
    world.agent.replies = ["Necesito que vuelvas a ingresar."]

    await world.inbound.handle(text_message())

    [reply] = world.whatsapp.texts()
    first, link = reply.split("\n\n")
    assert first == "Necesito que vuelvas a ingresar."
    assert verify_link_token(link.split("t=")[1]).purpose == "reauth"


async def test_placeholder_without_request_is_removed(world: World) -> None:
    world.agent.replies = ["Hola {{SIGN_IN_LINK}}"]

    await world.inbound.handle(text_message())

    assert world.whatsapp.texts() == ["Hola"]
    assert world.store.link_tokens == {}


def sign_in_completed(event_id: str = "evt-1") -> dict:
    return {
        "type": "system_event",
        "event": "sign_in_completed",
        "event_id": event_id,
        "wa_id": WA_ID,
        "timestamp": "2026-11-23T15:20:00Z",
        "data": {"customer_id": CUSTOMER_ID},
    }


async def test_sign_in_completed_runs_a_system_turn_inside_the_window(world: World) -> None:
    await world.inbound.handle(text_message())
    inbound_at = world.store.sessions[WA_ID].last_inbound_at
    world.link(timedelta(0))
    world.clock.advance(timedelta(minutes=5))
    world.agent.replies = ["¡Listo, ya estás vinculado!"]

    await world.inbound.handle(sign_in_completed())
    await world.inbound.handle(sign_in_completed())

    assert world.agent.turns[-1][1] == 'SYSTEM_EVENT {"event":"sign_in_completed"}'
    assert world.agent.state_at_turn[-1]["auth_fresh"] is True
    assert world.whatsapp.texts() == ["ok", "¡Listo, ya estás vinculado!"]
    assert world.store.sessions[WA_ID].last_inbound_at == inbound_at


async def test_system_event_reply_is_not_sent_outside_the_window(world: World) -> None:
    world.link(timedelta(0))

    await world.inbound.handle(sign_in_completed())

    assert len(world.agent.turns) == 1
    assert world.whatsapp.sent == []
