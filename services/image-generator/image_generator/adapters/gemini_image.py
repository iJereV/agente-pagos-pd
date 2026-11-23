"""ImageModel on Vertex AI through the google-genai SDK (Gemini image models)."""

from google import genai
from google.genai import types

PNG = "image/png"


class ImageGenerationError(RuntimeError):
    """The model returned no image (for example, blocked by safety filters)."""


class GeminiImageModel:
    def __init__(self, client: genai.Client, model: str) -> None:
        self._client = client
        self.name = model
        self._config = types.GenerateContentConfig(
            response_modalities=[types.Modality.TEXT, types.Modality.IMAGE],
            image_config=types.ImageConfig(aspect_ratio="1:1", output_mime_type=PNG),
        )

    def generate_png(self, prompt: str) -> bytes:
        response = self._client.models.generate_content(
            model=self.name, contents=prompt, config=self._config
        )
        for candidate in response.candidates or []:
            for part in (candidate.content.parts if candidate.content else None) or []:
                if part.inline_data and part.inline_data.data:
                    if part.inline_data.mime_type != PNG:
                        raise ImageGenerationError(
                            f"unexpected mime type {part.inline_data.mime_type}"
                        )
                    return part.inline_data.data
        raise ImageGenerationError("model returned no image")
