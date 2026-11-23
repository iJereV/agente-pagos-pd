"""TokenVerifier backed by `shared.tokens.verify_turn_token`."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from mcp_shop.domain.identity import Caller
from mcp_shop.ports.tokens import InvalidTurnToken


class TurnClaimsLike(Protocol):
    customer_id: str | None
    wa_id: str
    auth_fresh: bool
    last_receipt_ref: str | None


@dataclass(frozen=True)
class TurnTokenVerifier:
    verify_claims: Callable[[str], TurnClaimsLike]
    invalid_token_errors: tuple[type[Exception], ...]

    async def verify(self, token: str) -> Caller:
        try:
            # Verification may fetch the signer's JWKS; keep the event loop free.
            claims = await asyncio.to_thread(self.verify_claims, token)
        except self.invalid_token_errors as error:
            raise InvalidTurnToken(str(error)) from error
        return Caller(
            customer_id=claims.customer_id or None,
            wa_id=claims.wa_id,
            auth_fresh=claims.auth_fresh,
            last_receipt_ref=claims.last_receipt_ref or None,
        )


def shared_turn_token_verifier() -> TurnTokenVerifier:
    from shared.tokens import InvalidToken, verify_turn_token

    return TurnTokenVerifier(verify_turn_token, (InvalidToken,))
