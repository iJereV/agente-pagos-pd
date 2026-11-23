"""ReceiptStore backed by the private media bucket (`receipts/` prefix)."""

import asyncio
import mimetypes

from google.cloud import storage

from mcp_shop.ports.receipts import ReceiptFile, ReceiptNotFound


class GcsReceiptStore:
    def __init__(self, client: storage.Client, bucket_name: str) -> None:
        self._bucket = client.bucket(bucket_name)

    async def read(self, receipt_ref: str) -> ReceiptFile:
        return await asyncio.to_thread(self._read, receipt_ref)

    def _read(self, receipt_ref: str) -> ReceiptFile:
        blob = self._bucket.get_blob(receipt_ref)
        if blob is None:
            raise ReceiptNotFound(receipt_ref)
        mime_type = (
            blob.content_type or mimetypes.guess_type(receipt_ref)[0] or "application/octet-stream"
        )
        return ReceiptFile(data=blob.download_as_bytes(), mime_type=mime_type)
