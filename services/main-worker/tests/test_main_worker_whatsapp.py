import json

import httpx
from main_worker.adapters.whatsapp import GraphWhatsApp


async def test_link_button_is_a_cta_url_interactive_message() -> None:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.OUT"}]})

    http = httpx.AsyncClient(
        base_url="https://graph.example.test/v21.0", transport=httpx.MockTransport(record)
    )
    whatsapp = GraphWhatsApp(access_token="unused", phone_number_id="PNID_TEST", http=http)

    await whatsapp.send_link_button(
        "5490000000001", "Iniciá sesión:", "Iniciar sesión", "https://link.example.test/link?t=x"
    )

    [request] = requests
    assert request.url.path == "/v21.0/PNID_TEST/messages"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "540000000001",
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": "Iniciá sesión:"},
            "action": {
                "name": "cta_url",
                "parameters": {
                    "display_text": "Iniciar sesión",
                    "url": "https://link.example.test/link?t=x",
                },
            },
        },
    }
