"""Access rules every tool applies before touching data.

Each rule returns the caller's customer id when access is granted, or the closed
outcome that explains why not.
"""

from mcp_shop.application.outcomes import AUTH_REQUIRED, NOT_LINKED, Rejected
from mcp_shop.domain.identity import Caller


def linked_customer(caller: Caller) -> str | Rejected:
    return caller.customer_id or NOT_LINKED


def freshly_signed_in_customer(caller: Caller) -> str | Rejected:
    """Ordering and balance detail need a linked account and a recent Google sign-in."""
    if not caller.customer_id:
        return NOT_LINKED
    return caller.customer_id if caller.auth_fresh else AUTH_REQUIRED
