import base64
import json

import pytest
from shared.pubsub import InvalidPushMessage, decode_push


def envelope(data: bytes, attributes: dict[str, str] | None = None) -> dict:
    message = {"data": base64.b64encode(data).decode(), "messageId": "1"}
    if attributes is not None:
        message["attributes"] = attributes
    return {"message": message, "subscription": "projects/p/subscriptions/s"}


def test_decodes_payload_and_attributes() -> None:
    payload = {"type": "order_ready", "order_id": "ord_TEST"}
    body = envelope(json.dumps(payload).encode(), {"type": "order_ready"})

    assert decode_push(body) == (payload, {"type": "order_ready"})


def test_missing_attributes_decode_as_empty() -> None:
    assert decode_push(envelope(b'{"a": 1}')) == ({"a": 1}, {})


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"message": {}},
        {"message": {"data": "%%%not-base64"}},
        envelope(b"not json"),
        envelope(b"[1, 2]"),
    ],
)
def test_rejects_malformed_envelopes(body: dict) -> None:
    with pytest.raises(InvalidPushMessage):
        decode_push(body)
