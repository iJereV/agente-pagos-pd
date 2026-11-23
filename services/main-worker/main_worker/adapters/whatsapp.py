"""WhatsApp Cloud API client (Graph API) for the business phone number."""

import httpx

from main_worker.domain.errors import PermanentError, TransientError
from main_worker.domain.models import MediaFile

GRAPH_URL = "https://graph.facebook.com"


class GraphWhatsApp:
    def __init__(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        graph_version: str = "v21.0",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._phone_number_id = phone_number_id
        self._http = http or httpx.AsyncClient(
            base_url=f"{GRAPH_URL}/{graph_version}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=httpx.Timeout(30.0),
        )

    async def send_text(self, to: str, body: str) -> None:
        await self._send(to, {"type": "text", "text": {"body": body}})

    async def send_image(self, to: str, media_id: str) -> None:
        await self._send(to, {"type": "image", "image": {"id": media_id}})

    async def send_template(self, to: str, name: str, language: str) -> None:
        await self._send(
            to, {"type": "template", "template": {"name": name, "language": {"code": language}}}
        )

    async def upload_media(self, data: bytes, mime_type: str, filename: str) -> str:
        response = await self._request(
            "POST",
            f"/{self._phone_number_id}/media",
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": (filename, data, mime_type)},
        )
        return response.json()["id"]

    async def download_media(self, media_id: str) -> MediaFile:
        # The URL expires after a few minutes and needs the same bearer token.
        info = (await self._request("GET", f"/{media_id}")).json()
        content = await self._request("GET", info["url"])
        return MediaFile(data=content.content, mime_type=info.get("mime_type", ""))

    async def _send(self, to: str, message: dict) -> None:
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}
        await self._request("POST", f"/{self._phone_number_id}/messages", json=payload | message)

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            response = await self._http.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            raise TransientError(f"WhatsApp API unreachable: {exc}") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientError(f"WhatsApp API {response.status_code}")
        if response.is_error:
            raise PermanentError(f"WhatsApp API {response.status_code}: {_error_summary(response)}")
        return response


def _error_summary(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
    except ValueError:
        return response.text[:200]
    return f"code={error.get('code')} {error.get('message', '')}".strip()
