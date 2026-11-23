import base64
import json

import pytest
from fastapi.testclient import TestClient
from main_worker.api import create_app
from main_worker.domain.errors import TransientError
from main_worker_testkit import World, text_message


def push(payload: dict) -> dict:
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    return {"message": {"data": data, "attributes": {"type": payload.get("type", "")}}}


@pytest.fixture
def client(world: World) -> TestClient:
    return TestClient(create_app(world.inbound, world.deliveries))


def test_customer_message_is_acknowledged(client: TestClient, world: World) -> None:
    response = client.post("/pubsub/wa-inbound", json=push(text_message()))

    assert response.status_code == 204
    assert world.whatsapp.texts() == ["ok"]


@pytest.mark.parametrize("body", [{"message": {"data": "%%%"}}, {"unexpected": True}])
def test_malformed_push_is_acknowledged(client: TestClient, body: dict) -> None:
    assert client.post("/pubsub/wa-inbound", json=body).status_code == 204


def test_unknown_event_type_is_acknowledged(client: TestClient) -> None:
    assert client.post("/pubsub/wa-inbound", json=push({"type": "mystery"})).status_code == 204


def test_order_ready_without_images_is_acknowledged(client: TestClient) -> None:
    payload = {"type": "order_ready", "order_id": "ord_X", "wa_id": "5490000000001", "images": []}

    assert client.post("/pubsub/order-ready", json=push(payload)).status_code == 204


def test_transient_error_asks_pubsub_to_retry(client: TestClient, world: World) -> None:
    async def rate_limited(*_: object) -> None:
        raise TransientError("WhatsApp API 429")

    world.whatsapp.send_text = rate_limited

    response = client.post("/pubsub/wa-inbound", json=push(text_message()))

    assert response.status_code == 503
    assert world.store.processed == {}


def test_order_ready_push_reaches_the_delivery_use_case(client: TestClient, world: World) -> None:
    payload = {
        "type": "order_ready",
        "order_id": "ord_X",
        "customer_id": "uid-test-001",
        "wa_id": "5490000000001",
        "images": ["orders/ord_X/1.png"],
        "ready_at": "2026-11-23T15:15:02Z",
    }

    assert client.post("/pubsub/order-ready", json=push(payload)).status_code == 204
    assert world.store.deliveries["ord_X"]["status"] == "awaiting_window"
