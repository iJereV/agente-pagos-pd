"""Builders and constants shared by the main-worker tests (fixtures live in conftest)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from main_worker.application.conversation import Conversation
from main_worker.application.deliveries import OrderDeliveries
from main_worker.application.inbound import InboundHandler
from main_worker.domain.policy import Policy
from main_worker_fakes import FakeAgentRuntime, FakeChannelStore, FakeMediaStore, FakeWhatsApp
from shared.tokens import make_signer

WA_ID = "5490000000001"
CUSTOMER_ID = "uid-test-001"
NOW = datetime(2026, 11, 23, 15, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@dataclass
class World:
    store: FakeChannelStore
    media: FakeMediaStore
    whatsapp: FakeWhatsApp
    agent: FakeAgentRuntime
    clock: Clock
    inbound: InboundHandler
    deliveries: OrderDeliveries

    def link(self, signed_in_ago: timedelta | None = None) -> None:
        self.store.links[WA_ID] = CUSTOMER_ID
        if signed_in_ago is not None:
            self.store.sign_ins[CUSTOMER_ID] = self.clock() - signed_in_ago


def build_world() -> World:
    """All use cases wired to in-memory fakes and a controllable clock."""
    store, media, whatsapp, agent = (
        FakeChannelStore(),
        FakeMediaStore(),
        FakeWhatsApp(),
        FakeAgentRuntime(),
    )
    clock = Clock(NOW)
    policy = Policy(link_web_url="https://link.example.test")
    conversation = Conversation(
        store=store, agent=agent, signer=make_signer(), policy=policy, clock=clock
    )
    deliveries = OrderDeliveries(
        store=store,
        whatsapp=whatsapp,
        media=media,
        conversation=conversation,
        policy=policy,
        clock=clock,
    )
    inbound = InboundHandler(
        store=store,
        whatsapp=whatsapp,
        media=media,
        conversation=conversation,
        deliveries=deliveries,
        clock=clock,
    )
    return World(store, media, whatsapp, agent, clock, inbound, deliveries)


def text_message(text: str = "hola", wamid: str = "wamid.TEST1") -> dict:
    return {
        "type": "customer_message",
        "wamid": wamid,
        "wa_id": WA_ID,
        "timestamp": "2026-11-23T15:00:00Z",
        "message_type": "text",
        "text": text,
        "media_id": None,
        "mime_type": None,
        "profile_name": "Test Customer",
    }
