import pytest
from main_worker.domain.models import CustomerMessage
from main_worker.domain.rendering import (
    customer_turn_input,
    receipt_path,
    render_sign_in_link,
    system_event_input,
)

URL = "https://link.example.test/link?t=abc"


def test_placeholder_is_replaced() -> None:
    assert render_sign_in_link("Entrá: {{SIGN_IN_LINK}}", URL) == f"Entrá: {URL}"


def test_link_is_appended_when_placeholder_missing() -> None:
    assert render_sign_in_link("Necesito que ingreses. ", URL) == f"Necesito que ingreses.\n\n{URL}"


def test_empty_reply_becomes_the_link() -> None:
    assert render_sign_in_link("", URL) == URL


@pytest.mark.parametrize(
    ("message_type", "text", "expected"),
    [
        ("text", "hola", "hola"),
        ("image", None, "[image received]"),
        ("image", "comprobante", "[image received] comprobante"),
        ("document", None, "[document received]"),
        ("other", None, "[unsupported message received]"),
    ],
)
def test_customer_turn_input(message_type: str, text: str | None, expected: str) -> None:
    message = CustomerMessage(
        wamid="w", wa_id="5490000000001", message_type=message_type, text=text
    )

    assert customer_turn_input(message) == expected


def test_system_event_is_a_single_json_line() -> None:
    assert system_event_input("order_ready", order_id="ord_1", image_count=3) == (
        'SYSTEM_EVENT {"event":"order_ready","order_id":"ord_1","image_count":3}'
    )


@pytest.mark.parametrize(
    ("mime_type", "extension"),
    [
        ("image/jpeg", "jpg"),
        ("image/png", "png"),
        ("application/pdf", "pdf"),
        ("image/jpeg; charset=binary", "jpg"),
        ("application/x-unknown-thing", "bin"),
    ],
)
def test_receipt_path_extension(mime_type: str, extension: str) -> None:
    assert receipt_path("uid-1", "wamid.X", mime_type) == f"receipts/uid-1/wamid.X.{extension}"
