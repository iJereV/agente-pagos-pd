import hashlib
import hmac
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from wa_webhook.app import Settings, create_app

APP_SECRET = "test-app-secret-not-real"
VERIFY_TOKEN = "test-verify-token"
WA_ID = "5490000000001"


@pytest.fixture
def published() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def client(published: list[dict[str, Any]]) -> TestClient:
    return TestClient(create_app(Settings(APP_SECRET, VERIFY_TOKEN), published.append))


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()


def post(client: TestClient, payload: dict, signature: str | None = None):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    headers["X-Hub-Signature-256"] = signature if signature is not None else sign(body)
    return client.post("/webhook", content=body, headers=headers)


def notification(value: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA_TEST", "changes": [{"field": "messages", "value": value}]}],
    }


def message_value(*messages: dict) -> dict:
    return {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550000000", "phone_number_id": "PNID_TEST"},
        "contacts": [{"profile": {"name": "Test Customer"}, "wa_id": WA_ID}],
        "messages": list(messages),
    }


def test_verification_echoes_challenge(client: TestClient) -> None:
    response = client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "42"},
    )

    assert response.status_code == 200
    assert response.text == "42"


def test_verification_rejects_wrong_token(client: TestClient) -> None:
    response = client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"},
    )

    assert response.status_code == 403


@pytest.mark.parametrize("signature", ["", "sha256=deadbeef", "md5=whatever"])
def test_rejects_bad_signature(client: TestClient, published: list, signature: str) -> None:
    payload = notification(message_value())

    assert post(client, payload, signature).status_code == 401
    assert published == []


def test_text_message_is_published(client: TestClient, published: list) -> None:
    text = {
        "from": WA_ID,
        "id": "wamid.TEST1",
        "timestamp": "1795473000",
        "type": "text",
        "text": {"body": "quiero dos perritos"},
    }

    assert post(client, notification(message_value(text))).status_code == 200
    assert published == [
        {
            "type": "customer_message",
            "wamid": "wamid.TEST1",
            "wa_id": WA_ID,
            "timestamp": "2026-11-23T22:30:00Z",
            "message_type": "text",
            "text": "quiero dos perritos",
            "media_id": None,
            "mime_type": None,
            "profile_name": "Test Customer",
        }
    ]


def test_each_message_becomes_one_event(client: TestClient, published: list) -> None:
    image = {
        "from": WA_ID,
        "id": "wamid.IMG",
        "timestamp": "1795473000",
        "type": "image",
        "image": {"id": "MEDIA_1", "mime_type": "image/jpeg", "caption": "ya pagué"},
    }
    document = {
        "from": WA_ID,
        "id": "wamid.DOC",
        "timestamp": "1795473001",
        "type": "document",
        "document": {"id": "MEDIA_2", "mime_type": "application/pdf"},
    }
    sticker = {
        "from": WA_ID,
        "id": "wamid.STK",
        "timestamp": "1795473002",
        "type": "sticker",
        "sticker": {"id": "MEDIA_3", "mime_type": "image/webp"},
    }

    post(client, notification(message_value(image, document, sticker)))

    assert [(e["wamid"], e["message_type"], e["media_id"], e["text"]) for e in published] == [
        ("wamid.IMG", "image", "MEDIA_1", "ya pagué"),
        ("wamid.DOC", "document", "MEDIA_2", None),
        ("wamid.STK", "other", None, None),
    ]


def test_statuses_are_ignored(client: TestClient, published: list) -> None:
    statuses = {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": "PNID_TEST"},
        "statuses": [{"id": "wamid.OUT", "status": "delivered", "recipient_id": WA_ID}],
    }

    assert post(client, notification(statuses)).status_code == 200
    assert published == []


def test_failed_status_is_logged_without_recipient(
    client: TestClient, published: list, caplog: pytest.LogCaptureFixture
) -> None:
    statuses = {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": "PNID_TEST"},
        "statuses": [
            {
                "id": "wamid.OUT",
                "status": "failed",
                "recipient_id": WA_ID,
                "errors": [{"code": 131026, "title": "Message undeliverable"}],
            }
        ],
    }

    assert post(client, notification(statuses)).status_code == 200
    assert published == []
    [record] = [r for r in caplog.records if r.getMessage() == "outbound message failed"]
    assert record.error_code == 131026
    assert record.wamid == "wamid.OUT"
    assert WA_ID not in str(vars(record))


def test_invalid_json_with_valid_signature_is_rejected(client: TestClient) -> None:
    body = b"not json"
    response = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": sign(body)})

    assert response.status_code == 400
