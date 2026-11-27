import json

import httpx
import pytest
from mcp_shop.adapters.gemini_extractor import GeminiReceiptExtractor
from mcp_shop.adapters.vertex_maas_extractor import (
    VertexMaasReceiptExtractor,
    chat_completions_url,
)
from mcp_shop.bootstrap import build_extractor
from mcp_shop.config import Settings
from mcp_shop.domain.receipts import RawReceipt
from mcp_shop.ports.receipts import ExtractionUnavailable, ReceiptFile

MODEL = "meta/llama-4-maverick-17b-128e-instruct-maas"
URL = chat_completions_url("test-project", "us-east5")
RECEIPT = ReceiptFile(data=b"\x89PNG synthetic", mime_type="image/png")
FIELDS = {
    "is_receipt": True,
    "coelsa_id": "TESTCOELSA0001",
    "amount_text": "$ 4,00",
    "datetime_local_text": "26/11/2026 22:29",
    "origin_cuit": None,
    "destination_cvu": None,
    "bank_name": "Banco de Prueba",
}


def extractor_answering(response: httpx.Response) -> tuple[VertexMaasReceiptExtractor, list]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response

    async def token() -> str:
        return "test-token"

    http = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return VertexMaasReceiptExtractor(http, URL, MODEL, token), requests


def completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_regional_and_global_endpoints():
    assert URL == (
        "https://us-east5-aiplatform.googleapis.com/v1/projects/test-project"
        "/locations/us-east5/endpoints/openapi/chat/completions"
    )
    assert chat_completions_url("p", "global").startswith("https://aiplatform.googleapis.com/")


@pytest.mark.parametrize("content", [json.dumps(FIELDS), f"```json\n{json.dumps(FIELDS)}\n```"])
async def test_fields_are_read_from_the_model_answer(content: str):
    extractor, requests = extractor_answering(completion(content))

    raw = await extractor.extract(RECEIPT)

    assert raw == RawReceipt(**FIELDS)
    [request] = requests
    assert request.headers["authorization"] == "Bearer test-token"
    body = json.loads(request.content)
    assert body["model"] == MODEL and body["temperature"] == 0
    image = body["messages"][0]["content"][0]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, json=[{"error": {"code": 404, "message": "not enabled"}}]),
        httpx.Response(429, json={"error": {"code": 429}}),
        completion("No puedo leer esta imagen."),
        completion(json.dumps({"amount_text": "$ 4,00"})),
        httpx.Response(200, json={"choices": []}),
    ],
)
async def test_failures_become_extraction_unavailable(response: httpx.Response):
    extractor, _ = extractor_answering(response)

    with pytest.raises(ExtractionUnavailable):
        await extractor.extract(RECEIPT)


def settings_with(monkeypatch, **env: str) -> Settings:
    monkeypatch.setenv("MEDIA_BUCKET", "media")
    monkeypatch.setenv("ORDER_CREATED_TOPIC", "order-created")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings.from_env()


def test_open_model_ids_use_the_vertex_maas_extractor(monkeypatch):
    settings = settings_with(monkeypatch, EXTRACTION_MODEL=MODEL)
    assert isinstance(build_extractor(settings), VertexMaasReceiptExtractor)


def test_bare_ids_use_gemini(monkeypatch):
    settings = settings_with(
        monkeypatch, EXTRACTION_MODEL="gemini-3.5-flash", EXTRACTION_MODEL_LOCATION="global"
    )
    assert isinstance(build_extractor(settings), GeminiReceiptExtractor)
