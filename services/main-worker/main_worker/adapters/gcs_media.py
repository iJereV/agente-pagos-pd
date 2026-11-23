"""``MediaStore`` on the private media bucket."""

import asyncio

from google.api_core.exceptions import NotFound
from google.cloud import storage

from main_worker.domain.errors import PermanentError


class GcsMediaStore:
    def __init__(self, client: storage.Client, bucket: str) -> None:
        self._bucket = client.bucket(bucket)

    async def put(self, path: str, data: bytes, content_type: str) -> None:
        blob = self._bucket.blob(path)
        await asyncio.to_thread(blob.upload_from_string, data, content_type=content_type)

    async def get(self, path: str) -> bytes:
        try:
            return await asyncio.to_thread(self._bucket.blob(path).download_as_bytes)
        except NotFound as exc:
            raise PermanentError(f"media object not found: {path}") from exc
