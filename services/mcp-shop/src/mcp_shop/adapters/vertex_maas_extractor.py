"""ReceiptExtractor backed by an open vision model on Vertex AI (Model-as-a-Service).

Open models such as Llama 4 are called through Vertex AI's OpenAI-compatible chat
completions endpoint. They run on the same billing as gpt-oss, unlike Gemini, which
needs a paid billing account. The model only copies what is printed; the JSON it returns
is validated against `ReceiptFields`, and anything else is treated as unavailable.
"""

import base64
import json
import re
from collections.abc import Awaitable, Callable

import httpx
from pydantic import ValidationError

from mcp_shop.adapters.receipt_fields import PROMPT, ReceiptFields
from mcp_shop.domain.receipts import RawReceipt
from mcp_shop.ports.receipts import ExtractionUnavailable, ReceiptFile

SCHEMA_HINT = (
    "Answer with one JSON object and nothing else, with exactly these keys: "
    + json.dumps(list(ReceiptFields.model_fields))
    + ". is_receipt is true or false; every other value is a string or null."
)
_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def chat_completions_url(project: str, location: str) -> str:
    host = (
        "aiplatform.googleapis.com"
        if location == "global"
        else f"{location}-aiplatform.googleapis.com"
    )
    return f"https://{host}/v1/projects/{project}/locations/{location}/endpoints/openapi/chat/completions"


class VertexMaasReceiptExtractor:
    def __init__(
        self,
        http: httpx.AsyncClient,
        url: str,
        model: str,
        access_token: Callable[[], Awaitable[str]],
    ) -> None:
        self._http = http
        self._url = url
        self._model = model
        self._access_token = access_token

    async def extract(self, receipt: ReceiptFile) -> RawReceipt:
        image = base64.b64encode(receipt.data).decode()
        body = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": 512,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{receipt.mime_type};base64,{image}"},
                        },
                        {"type": "text", "text": f"{PROMPT}\n{SCHEMA_HINT}"},
                    ],
                }
            ],
        }
        try:
            response = await self._http.post(
                self._url,
                json=body,
                headers={"Authorization": f"Bearer {await self._access_token()}"},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"] or ""
            fields = ReceiptFields.model_validate_json(_CODE_FENCE.sub("", content.strip()))
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            ValidationError,
        ) as exc:
            raise ExtractionUnavailable(f"{self._model}: {type(exc).__name__}") from exc
        return RawReceipt(**fields.model_dump())
