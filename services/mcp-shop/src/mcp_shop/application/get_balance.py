"""Use case: show the caller's debt, credit balance and unpaid orders."""

from dataclasses import dataclass

from mcp_shop.application.access import freshly_signed_in_customer
from mcp_shop.application.outcomes import Balance, Rejected, UnpaidOrder
from mcp_shop.domain.identity import Caller
from mcp_shop.ports.repository import ShopRepository


@dataclass(frozen=True)
class GetBalance:
    repository: ShopRepository
    credit_limit_cents: int

    async def __call__(self, caller: Caller) -> Balance | Rejected:
        customer_id = freshly_signed_in_customer(caller)
        if isinstance(customer_id, Rejected):
            return customer_id
        ledger = await self.repository.load_ledger(customer_id)
        return Balance(
            debt_cents=ledger.debt_cents,
            credit_balance_cents=ledger.credit_balance_cents,
            available_credit_cents=ledger.available_credit_cents(self.credit_limit_cents),
            unpaid_orders=[
                UnpaidOrder(
                    order_id=order.order_id,
                    total_cents=order.total_cents,
                    paid_cents=order.paid_cents,
                    created_at=order.created_at,
                )
                for order in ledger.unpaid_orders
            ],
        )
