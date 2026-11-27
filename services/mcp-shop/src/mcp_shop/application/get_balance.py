"""Use case: show the caller's prepaid balance, granting the welcome credit if due."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from mcp_shop.application.access import freshly_signed_in_customer
from mcp_shop.application.ids import utc_now
from mcp_shop.application.outcomes import Balance, Rejected
from mcp_shop.domain.identity import Caller
from mcp_shop.domain.ledger import Ledger
from mcp_shop.ports.repository import ShopRepository


@dataclass(frozen=True)
class GetBalance:
    repository: ShopRepository
    welcome_credit_cents: int
    clock: Callable[[], datetime] = utc_now

    async def __call__(self, caller: Caller) -> Balance | Rejected:
        customer_id = freshly_signed_in_customer(caller)
        if isinstance(customer_id, Rejected):
            return customer_id
        now = self.clock()

        def welcome(ledger: Ledger) -> None:
            ledger.grant_welcome_credit(self.welcome_credit_cents, now)

        ledger = await self.repository.update_ledger(customer_id, welcome)
        return Balance(
            balance_cents=ledger.balance_cents,
            welcome_credit_cents=ledger.welcome_credit_granted_now_cents,
        )
