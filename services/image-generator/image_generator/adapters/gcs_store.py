"""MediaStore on Cloud Storage. Conditional writes use generation preconditions."""

import json
from typing import Any

from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage


class GcsMediaStore:
    def __init__(self, client: storage.Client, bucket_name: str) -> None:
        self._bucket = client.bucket(bucket_name)

    def read_json(self, path: str) -> dict[str, Any] | None:
        blob = self._bucket.get_blob(path)
        return None if blob is None else json.loads(blob.download_as_bytes())

    def read_json_versioned(self, path: str) -> tuple[dict[str, Any] | None, int]:
        blob = self._bucket.get_blob(path)
        if blob is None:
            return None, 0
        # Pin the read to the generation we report, so data and generation agree.
        data = blob.download_as_bytes(if_generation_match=blob.generation)
        return json.loads(data), blob.generation

    def write_json(self, path: str, data: dict[str, Any]) -> None:
        self._bucket.blob(path).upload_from_string(_dump(data), content_type="application/json")

    def write_json_if_generation(self, path: str, data: dict[str, Any], generation: int) -> bool:
        try:
            self._bucket.blob(path).upload_from_string(
                _dump(data), content_type="application/json", if_generation_match=generation
            )
        except PreconditionFailed:
            return False
        return True

    def write_bytes(self, path: str, data: bytes, content_type: str) -> None:
        self._bucket.blob(path).upload_from_string(data, content_type=content_type)


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)
