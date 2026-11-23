"""In-memory fakes for every port and synthetic builders. No real data."""

import copy
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from mcp_shop.adapters.simulated import SimulatedTransferVerifier
from mcp_shop.application.create_order import CreateOrder
from mcp_shop.application.get_balance import GetBalance
from mcp_shop.application.get_order_status import GetOrderStatus
from mcp_shop.application.order_events import OrderEvents
from mcp_shop.application.shop import Shop
from mcp_shop.application.verify_receipt import VerifyReceipt
from mcp_shop.domain.catalog import Animal, OrderLine
from mcp_shop.domain.identity import Caller
from mcp_shop.domain.ledger import Ledger, PlacedOrder
from mcp_shop.domain.orders import Order, OrderStatus
from mcp_shop.domain.payments import ManualReview, PaymentAlreadyRecorded, RecordedPayment
from mcp_shop.domain.receipts import RawReceipt
from mcp_shop.domain.transfers import IncomingTransfer
from mcp_shop.ports.receipts import ReceiptFile, ReceiptNotFound
from mcp_shop.ports.tokens import InvalidTurnToken

NOW = datetime(2026, 11, 23, 18, 0, tzinfo=UTC)
CUSTOMER = "cust-synthetic-1"
WA_ID = "5490000000001"
RECEIPT_REF = f"receipts/{CUSTOMER}/wamid.synthetic1.jpg"
PAYER_CUIT = "20000000001"


def caller(
    *, customer_id: str | None = CUSTOMER, auth_fresh: bool = True, receipt: str | None = None
) -> Caller:
    return Caller(
        customer_id=customer_id, wa_id=WA_ID, auth_fresh=auth_fresh, last_receipt_ref=receipt
    )


def order(order_id: str, total: int, paid: int = 0, minutes_ago: int = 60) -> Order:
    return Order(
        order_id=order_id,
        customer_id=CUSTOMER,
        wa_id=WA_ID,
        lines=(OrderLine(Animal.DOG, 1),),
        total_cents=total,
        paid_cents=paid,
        created_at=NOW - timedelta(minutes=minutes_ago),
    )


def transfer(
    e2e_id: str | None = "SYNTHCOELSA00000000000001",
    amount: int = 500,
    received_at: datetime = NOW - timedelta(minutes=10),
    payer_cuit: str | None = PAYER_CUIT,
    payment_id: str = "sim-1",
) -> IncomingTransfer:
    return IncomingTransfer(
        provider="simulated",
        provider_payment_id=payment_id,
        e2e_id=e2e_id,
        amount_cents=amount,
        received_at=received_at,
        payer_cuit=payer_cuit,
    )


class InMemoryShopRepository:
    """Mirrors the transactional contract: work on a copy, commit only on success."""

    def __init__(self) -> None:
        self.credit: dict[str, int] = {}
        self.orders: dict[str, Order] = {}
        self.payments: dict[str, RecordedPayment] = {}
        self.reviews: dict[str, ManualReview] = {}
        self.pending_events: set[str] = set()

    def add_order(self, new: Order) -> None:
        self.orders[new.order_id] = new

    async def load_ledger(self, customer_id: str) -> Ledger:
        unpaid = sorted(
            (
                copy.deepcopy(o)
                for o in self.orders.values()
                if o.customer_id == customer_id and o.status != OrderStatus.PAID
            ),
            key=lambda o: o.created_at,
        )
        return Ledger(customer_id, self.credit.get(customer_id, 0), unpaid)

    async def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    async def place_order(
        self, customer_id: str, place: Callable[[Ledger], PlacedOrder]
    ) -> PlacedOrder:
        ledger = await self.load_ledger(customer_id)
        placed = place(ledger)
        self.orders[placed.order.order_id] = placed.order
        self.pending_events.add(placed.order.order_id)
        self.credit[customer_id] = ledger.credit_balance_cents
        return placed

    async def orders_pending_event(self, customer_id: str) -> list[Order]:
        return sorted(
            (
                o
                for o in self.orders.values()
                if o.order_id in self.pending_events and o.customer_id == customer_id
            ),
            key=lambda o: o.created_at,
        )

    async def mark_event_published(self, order_id: str) -> None:
        self.pending_events.discard(order_id)

    async def record_payment(
        self, customer_id: str, payment_key: str, apply: Callable[[Ledger], RecordedPayment]
    ) -> RecordedPayment:
        if payment_key in self.payments:
            raise PaymentAlreadyRecorded(payment_key)
        ledger = await self.load_ledger(customer_id)
        payment = apply(ledger)
        self.payments[payment_key] = payment
        for updated in ledger.unpaid_orders:
            self.orders[updated.order_id] = updated
        self.credit[customer_id] = ledger.credit_balance_cents
        return payment

    async def save_manual_review(self, review: ManualReview) -> None:
        self.reviews[review.review_id] = review


class FakeTokens:
    def __init__(self) -> None:
        self.callers: dict[str, Caller] = {}

    async def verify(self, token: str) -> Caller:
        if token not in self.callers:
            raise InvalidTurnToken("unknown token")
        return self.callers[token]


class FakeReceiptStore:
    def __init__(self) -> None:
        self.files: dict[str, ReceiptFile] = {}

    async def read(self, receipt_ref: str) -> ReceiptFile:
        if receipt_ref not in self.files:
            raise ReceiptNotFound(receipt_ref)
        return self.files[receipt_ref]


class FakeExtractor:
    def __init__(self) -> None:
        self.result = RawReceipt(is_receipt=False)

    async def extract(self, receipt: ReceiptFile) -> RawReceipt:
        return self.result


class FakePublisher:
    def __init__(self) -> None:
        self.orders: list[Order] = []
        self.failures_left = 0

    async def order_created(self, created: Order) -> None:
        if self.failures_left:
            self.failures_left -= 1
            raise RuntimeError("synthetic publish failure")
        self.orders.append(created)


class World:
    def __init__(self) -> None:
        self.repository = InMemoryShopRepository()
        self.tokens = FakeTokens()
        self.receipts = FakeReceiptStore()
        self.extractor = FakeExtractor()
        self.publisher = FakePublisher()
        self.transfers = SimulatedTransferVerifier()
        self.sleeps: list[float] = []
        order_events = OrderEvents(self.repository, self.publisher, sleep=self._sleep)
        self.shop = Shop(
            tokens=self.tokens,
            order_events=order_events,
            balance=GetBalance(self.repository, credit_limit_cents=1000),
            ordering=CreateOrder(
                self.repository,
                order_events,
                credit_limit_cents=1000,
                new_order_id=self._next_order_id,
                clock=lambda: NOW,
            ),
            receipts=VerifyReceipt(
                repository=self.repository,
                receipts=self.receipts,
                extractor=self.extractor,
                transfers=self.transfers,
                match_window=timedelta(minutes=120),
                clock=lambda: NOW,
            ),
            order_status=GetOrderStatus(self.repository),
        )
        self._sequence = 0

    async def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def _next_order_id(self) -> str:
        self._sequence += 1
        return f"ord_test{self._sequence}"

    def receipt(self, raw: RawReceipt) -> None:
        self.receipts.files[RECEIPT_REF] = ReceiptFile(b"synthetic-image", "image/jpeg")
        self.extractor.result = raw
