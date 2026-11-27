import base64
import io
import json

import httpx
import pytest
from image_generator.adapters.cloudflare_image import (
    PNG_SIGNATURE,
    CloudflareImageError,
    CloudflareImageModel,
)
from image_generator.adapters.gemini_image import GeminiImageModel
from image_generator.image_models import build_image_model
from PIL import Image

MODEL = "@cf/black-forest-labs/flux-1-schnell"


def image_bytes(fmt: str) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 120, 40)).save(out, format=fmt)
    return out.getvalue()


def model_answering(handler) -> tuple[CloudflareImageModel, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    return CloudflareImageModel(client, "acct-test", MODEL), seen


def ok(data: bytes) -> httpx.Response:
    payload = {"success": True, "result": {"image": base64.b64encode(data).decode()}}
    return httpx.Response(200, json=payload)


def test_jpeg_from_workers_ai_is_returned_as_png():
    model, seen = model_answering(lambda _: ok(image_bytes("JPEG")))

    png = model.generate_png("a capybara in a hat")

    assert png.startswith(PNG_SIGNATURE)
    [request] = seen
    assert request.url.path == f"/client/v4/accounts/acct-test/ai/run/{MODEL}"
    assert json.loads(request.content) == {"prompt": "a capybara in a hat", "steps": 4}


def test_png_from_workers_ai_is_kept_as_is():
    png = image_bytes("PNG")
    model, _ = model_answering(lambda _: ok(png))

    assert model.generate_png("a penguin") == png


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(
            429, json={"success": False, "errors": [{"code": 3036, "message": "quota"}]}
        ),
        httpx.Response(200, json={"success": False, "errors": []}),
        httpx.Response(200, json={"success": True, "result": {}}),
        httpx.Response(200, json={"success": True, "result": {"image": "not base64!"}}),
        httpx.Response(502, text="bad gateway"),
    ],
)
def test_failures_raise(response: httpx.Response):
    model, _ = model_answering(lambda _: response)

    with pytest.raises(CloudflareImageError):
        model.generate_png("a dog")


def test_quota_error_names_the_code():
    body = {"success": False, "errors": [{"code": 3036, "message": "daily free allocation used"}]}
    model, _ = model_answering(lambda _: httpx.Response(429, json=body))

    with pytest.raises(CloudflareImageError, match="429: 3036 daily free allocation used"):
        model.generate_png("a dog")


def test_cloudflare_model_ids_select_workers_ai(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-test")

    model = build_image_model(MODEL)

    assert isinstance(model, CloudflareImageModel)
    assert model.name == MODEL


def test_other_model_ids_select_gemini(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

    assert isinstance(build_image_model("gemini-3.1-flash-lite-image"), GeminiImageModel)
