"""Who is calling, as asserted by the signed turn token. Never by tool arguments."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Caller:
    customer_id: str | None
    wa_id: str
    auth_fresh: bool
    last_receipt_ref: str | None

    @property
    def is_linked(self) -> bool:
        return bool(self.customer_id)
