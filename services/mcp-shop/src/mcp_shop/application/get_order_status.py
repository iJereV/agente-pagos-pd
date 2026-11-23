"""Use case: payment status of one of the caller's orders."""

from dataclasses import dataclass

from mcp_shop.application.access import linked_customer
from mcp_shop.application.outcomes import OrderStatusView, Rejected
from mcp_shop.domain.identity import Caller
from mcp_shop.ports.repository import ShopRepository


@dataclass(frozen=True)
class GetOrderStatus:
    repository: ShopRepository

    async def __call__(self, caller: Caller, order_id: str) -> OrderStatusView | Rejected:
        customer_id = linked_customer(caller)
        if isinstance(customer_id, Rejected):
            return customer_id
        order = await self.repository.get_order(order_id)
        # Someone else's order is indistinguishable from a missing one.
        if order is None or order.customer_id != customer_id:
            return Rejected(status="not_found")
        return OrderStatusView(
            order_status=order.status.value,
            total_cents=order.total_cents,
            paid_cents=order.paid_cents,
        )
