"""Ports to read a receipt image and extract its printed fields."""

from dataclasses import dataclass
from typing import Protocol

from mcp_shop.domain.receipts import RawReceipt


@dataclass(frozen=True)
class ReceiptFile:
    data: bytes
    mime_type: str


class ReceiptNotFound(Exception):
    pass


class ReceiptStore(Protocol):
    async def read(self, receipt_ref: str) -> ReceiptFile:
        """Raises `ReceiptNotFound` when nothing is stored under `receipt_ref`."""
        ...


class ExtractionUnavailable(Exception):
    """The model could not be reached or did not answer in the expected shape."""


class ReceiptExtractor(Protocol):
    async def extract(self, receipt: ReceiptFile) -> RawReceipt:
        """Raises `ExtractionUnavailable` when the receipt cannot be read right now."""
        ...
