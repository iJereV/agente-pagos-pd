"""ImageModel on Cloudflare Workers AI text-to-image models (for example FLUX.1 [schnell]).

Workers AI returns the image base64-encoded (FLUX.1 [schnell] returns a JPEG); it is
re-encoded as PNG because the rest of the system stores and sends PNG.
"""

import base64
import binascii
import io

import httpx
from PIL import Image

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RUN_URL = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"


class CloudflareImageError(RuntimeError):
    """Workers AI rejected the request or returned no usable image."""


class CloudflareImageModel:
    def __init__(self, client: httpx.Client, account_id: str, model: str, steps: int = 4) -> None:
        self._client = client
        self._url = RUN_URL.format(account_id=account_id, model=model)
        self._steps = steps
        self.name = model

    def generate_png(self, prompt: str) -> bytes:
        response = self._client.post(self._url, json={"prompt": prompt, "steps": self._steps})
        body = _json_or_empty(response)
        if response.is_error or body.get("success") is False:
            raise CloudflareImageError(f"workers ai {response.status_code}: {_errors(body)}")
        image = (body.get("result") or {}).get("image")
        if not image:
            raise CloudflareImageError("workers ai returned no image")
        try:
            return to_png(base64.b64decode(image, validate=True))
        except (binascii.Error, OSError) as exc:
            raise CloudflareImageError("workers ai returned an unreadable image") from exc


def to_png(data: bytes) -> bytes:
    if data.startswith(PNG_SIGNATURE):
        return data
    with Image.open(io.BytesIO(data)) as image:
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()


def _json_or_empty(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _errors(body: dict) -> str:
    errors = body.get("errors") or []
    return "; ".join(f"{e.get('code')} {e.get('message')}" for e in errors if isinstance(e, dict))
