from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from mcp_shop.adapters.mercadopago import MercadoPagoTransferVerifier, to_incoming_transfer
from mcp_shop.adapters.pubsub_publisher import PubSubEventPublisher, order_created_payload
from mcp_shop.adapters.simulated import SimulatedTransferVerifier
from mcp_shop.adapters.turn_token import TurnTokenVerifier
from mcp_shop.ports.tokens import InvalidTurnToken
from shop_fakes import order

COLLECTOR = "100000001"


def mp_payment(**overrides):
    payment = {
        "id": 900000001,
        "status": "approved",
        "collector_id": int(COLLECTOR),
        "operation_type": "account_fund",
        "payment_method_id": "cvu",
        "payment_type_id": "bank_transfer",
        "transaction_amount": 2166.35,
        "date_created": "2026-11-23T11:14:10.000-04:00",
        "transaction_details": {"transaction_id": "SYNTHCOELSA0001", "bank_transfer_id": 1},
        "point_of_interaction": {"transaction_data": {"e2e_id": "SYNTHCOELSA0001"}},
        "payer": {"identification": {"type": "CUIT", "number": "20000000001"}},
    }
    payment.update(overrides)
    return payment


def test_mercadopago_bank_transfer_maps_to_utc_cents():
    transfer = to_incoming_transfer(mp_payment(), COLLECTOR)
    assert transfer is not None
    assert transfer.provider_payment_id == "900000001"
    assert transfer.e2e_id == "SYNTHCOELSA0001"
    assert transfer.amount_cents == 216635
    assert transfer.received_at == datetime(2026, 11, 23, 15, 14, 10, tzinfo=UTC)
    assert transfer.payer_cuit == "20000000001"


def test_mercadopago_wallet_transfer_without_payer_id_is_kept():
    transfer = to_incoming_transfer(
        mp_payment(operation_type="money_transfer", payment_method_id="account_money", payer={}),
        COLLECTOR,
    )
    assert transfer is not None and transfer.payer_cuit is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"payment_method_id": "consumer_credits"},
        {"collector_id": 999},
        {"status": "pending"},
        {"operation_type": "regular_payment", "payment_method_id": "visa"},
    ],
)
def test_mercadopago_non_incoming_payments_are_dropped(overrides):
    assert to_incoming_transfer(mp_payment(**overrides), COLLECTOR) is None


async def test_mercadopago_search_sends_range_and_bearer():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "results": [mp_payment(), mp_payment(id=2, payment_method_id="consumer_credits")],
                "paging": {"total": 2, "limit": 100, "offset": 0},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        verifier = MercadoPagoTransferVerifier(http, "synthetic-token", COLLECTOR)
        transfers = await verifier.incoming_transfers(
            datetime(2026, 11, 21, tzinfo=UTC), datetime(2026, 11, 23, 18, tzinfo=UTC)
        )

    assert [t.provider_payment_id for t in transfers] == ["900000001"]
    [request] = seen
    assert request.headers["authorization"] == "Bearer synthetic-token"
    assert request.url.params["range"] == "date_created"
    assert request.url.params["begin_date"] == "2026-11-21T00:00:00.000Z"
    assert request.url.params["end_date"] == "2026-11-23T18:00:00.000Z"
    assert request.url.params["sort"] == "date_created"
    assert request.url.params["criteria"] == "desc"


async def test_order_created_message_matches_the_contract():
    sent: list[tuple[str, dict]] = []
    publisher = PubSubEventPublisher(
        lambda topic, payload: sent.append((topic, payload)) or "1", "t"
    )
    placed = order("ord_x", 100)
    await publisher.order_created(placed)
    assert sent == [("t", order_created_payload(placed))]
    assert order_created_payload(placed) == {
        "type": "order_created",
        "order_id": "ord_x",
        "customer_id": placed.customer_id,
        "wa_id": placed.wa_id,
        "items": [{"animal": "dog", "qty": 1}],
        "created_at": "2026-11-23T17:00:00Z",
    }


@dataclass(frozen=True)
class SyntheticClaims:
    customer_id: str | None
    wa_id: str
    auth_fresh: bool
    last_receipt_ref: str | None


class SyntheticInvalidToken(Exception):
    pass


async def test_turn_token_claims_become_the_caller():
    def verify(token: str) -> SyntheticClaims:
        if token != "good":
            raise SyntheticInvalidToken
        return SyntheticClaims("", "5490000000001", False, None)

    verifier = TurnTokenVerifier(verify, (SyntheticInvalidToken,))
    caller = await verifier.verify("good")
    assert caller.customer_id is None and not caller.is_linked
    with pytest.raises(InvalidTurnToken):
        await verifier.verify("bad")


async def test_simulated_fixture_loads_and_filters_by_time():
    verifier = SimulatedTransferVerifier.from_fixture()
    found = await verifier.incoming_transfers(
        datetime(2026, 11, 23, tzinfo=UTC), datetime(2026, 11, 23, 23, tzinfo=UTC)
    )
    assert [t.provider_payment_id for t in found] == ["sim-1001", "sim-1002"]
