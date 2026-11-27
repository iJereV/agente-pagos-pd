"""ReceiptExtractor backed by Gemini on Vertex AI with a strict response schema.

The model only copies what is printed. Amounts and times are parsed by domain code.
Gemini needs a paid billing account; open models go through `vertex_maas_extractor`.
"""

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from mcp_shop.adapters.receipt_fields import PROMPT, ReceiptFields
from mcp_shop.domain.receipts import RawReceipt
from mcp_shop.ports.receipts import ExtractionUnavailable, ReceiptFile


class GeminiReceiptExtractor:
    def __init__(self, client: genai.Client, model: str) -> None:
        self._client = client
        self._model = model

    async def extract(self, receipt: ReceiptFile) -> RawReceipt:
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=receipt.data, mime_type=receipt.mime_type),
                    PROMPT,
                ],
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=ReceiptFields,
                ),
            )
            fields = ReceiptFields.model_validate_json(response.text or "")
        except (errors.APIError, ValidationError) as exc:
            raise ExtractionUnavailable(f"{self._model}: {type(exc).__name__}") from exc
        return RawReceipt(**fields.model_dump())
