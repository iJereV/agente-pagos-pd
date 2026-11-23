"""Payment allocation: oldest unpaid order first, the remainder becomes credit."""

from dataclasses import dataclass

from mcp_shop.domain.orders import Order


@dataclass(frozen=True)
class Allocation:
    order_id: str
    amount_cents: int


@dataclass(frozen=True)
class AllocationResult:
    allocations: tuple[Allocation, ...]
    remainder_cents: int


def allocate(amount_cents: int, orders: list[Order]) -> AllocationResult:
    """Apply `amount_cents` to `orders` oldest first. Mutates the orders it pays."""
    if amount_cents <= 0:
        raise ValueError("amount must be positive")
    allocations: list[Allocation] = []
    left = amount_cents
    for order in sorted(orders, key=lambda o: o.created_at):
        if left == 0:
            break
        share = min(left, order.outstanding_cents)
        if share == 0:
            continue
        order.pay(share)
        allocations.append(Allocation(order.order_id, share))
        left -= share
    return AllocationResult(tuple(allocations), left)
