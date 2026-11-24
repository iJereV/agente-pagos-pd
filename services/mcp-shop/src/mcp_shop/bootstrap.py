"""Composition root: picks the adapters for each port from the settings."""

import httpx
from google import genai
from google.cloud import storage

from mcp_shop.adapters.firestore_repository import FirestoreShopRepository
from mcp_shop.adapters.gcs_receipts import GcsReceiptStore
from mcp_shop.adapters.gemini_extractor import GeminiReceiptExtractor
from mcp_shop.adapters.mercadopago import MercadoPagoTransferVerifier
from mcp_shop.adapters.pubsub_publisher import shared_event_publisher
from mcp_shop.adapters.simulated import SimulatedTransferVerifier
from mcp_shop.adapters.turn_token import shared_turn_token_verifier
from mcp_shop.application.create_order import CreateOrder
from mcp_shop.application.get_balance import GetBalance
from mcp_shop.application.get_order_status import GetOrderStatus
from mcp_shop.application.order_events import OrderEvents
from mcp_shop.application.shop import Shop
from mcp_shop.application.verify_receipt import VerifyReceipt
from mcp_shop.config import Settings
from mcp_shop.ports.transfers import TransferVerifier

MP_TIMEOUT_SECONDS = 10.0


def build_shop(settings: Settings) -> Shop:
    repository = FirestoreShopRepository.for_database(settings.project, settings.shop_database)
    order_events = OrderEvents(repository, shared_event_publisher(settings.order_created_topic))
    return Shop(
        tokens=shared_turn_token_verifier(),
        order_events=order_events,
        balance=GetBalance(repository, settings.credit_limit_cents),
        ordering=CreateOrder(repository, order_events, settings.credit_limit_cents),
        receipts=VerifyReceipt(
            repository=repository,
            receipts=GcsReceiptStore(
                storage.Client(project=settings.project), settings.media_bucket
            ),
            extractor=GeminiReceiptExtractor(
                genai.Client(
                    vertexai=True,
                    project=settings.project,
                    location=settings.extraction_model_location,
                ),
                settings.extraction_model,
            ),
            transfers=_transfer_verifier(settings),
            match_window=settings.match_window,
        ),
        order_status=GetOrderStatus(repository),
    )


def _transfer_verifier(settings: Settings) -> TransferVerifier:
    if settings.transfer_verifier == "simulated":
        return SimulatedTransferVerifier.from_fixture(settings.simulated_transfers_path)
    if not settings.mp_access_token or not settings.mp_collector_id:
        raise ValueError("MP_ACCESS_TOKEN and MP_COLLECTOR_ID are required for mercadopago")
    return MercadoPagoTransferVerifier(
        httpx.AsyncClient(timeout=MP_TIMEOUT_SECONDS),
        settings.mp_access_token,
        settings.mp_collector_id,
    )
