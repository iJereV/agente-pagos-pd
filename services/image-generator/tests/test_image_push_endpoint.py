import pytest
from fastapi.testclient import TestClient
from image_fakes import order_payload, push_envelope
from image_generator.app import create_app
from shared.pubsub import decode_push


@pytest.fixture
def client(make_service, store) -> TestClient:
    return TestClient(create_app(make_service(store), decode_push))


def test_valid_event_is_processed(client, publisher):
    response = client.post("/pubsub/order-created", json=push_envelope(order_payload()))

    assert response.status_code == 200
    assert response.json() == {"status": "generated"}
    assert len(publisher.published) == 1


@pytest.mark.parametrize(
    "payload",
    [
        order_payload(type="order_ready"),
        order_payload(items=[]),
        order_payload(items=[{"animal": "cat", "qty": 1}]),
        order_payload(items=[{"animal": "dog", "qty": 6}]),
        order_payload(items=[{"animal": "dog", "qty": 0}]),
        order_payload(order_id="../../etc"),
        order_payload(created_at="2026-11-23T15:14:10"),
        {"type": "order_created"},
    ],
)
def test_invalid_payload_is_rejected_without_side_effects(client, payload, store, publisher):
    response = client.post("/pubsub/order-created", json=push_envelope(payload))

    assert response.status_code == 400
    assert store.objects == {}
    assert publisher.published == []


def test_malformed_envelope_is_rejected(client):
    assert client.post("/pubsub/order-created", json={"message": {}}).status_code == 400
