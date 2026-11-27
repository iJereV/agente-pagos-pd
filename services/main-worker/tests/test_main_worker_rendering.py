import pytest
from main_worker.domain.models import CustomerMessage
from main_worker.domain.rendering import (
    customer_turn_input,
    receipt_path,
    strip_sign_in_placeholder,
    system_event_input,
)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("Entrá: {{SIGN_IN_LINK}}", "Entrá:"),
        ("Ingresá acá {{SIGN_IN_LINK}} y volvé.", "Ingresá acá y volvé."),
        ("Iniciá sesión:\n\n{{SIGN_IN_LINK}}\n\nTe espero.", "Iniciá sesión:\n\nTe espero."),
        ("{{SIGN_IN_LINK}}", ""),
        ("Sin marcador.", "Sin marcador."),
    ],
)
def test_placeholder_is_removed_cleanly(reply: str, expected: str) -> None:
    assert strip_sign_in_placeholder(reply) == expected


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
