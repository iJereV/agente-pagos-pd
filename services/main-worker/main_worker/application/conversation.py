"""One agent turn: identity, session, turn token, the turn itself and the sign-in link."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from shared.tokens import (
    LINK_TOKEN_TTL_SECONDS,
    TokenSigner,
    issue_link_token,
    issue_turn_token,
)

from main_worker.application import Clock
from main_worker.domain.errors import SessionNotFound
from main_worker.domain.models import Identity, SessionPointer
from main_worker.domain.policy import Policy, window_open
from main_worker.domain.rendering import (
    SIGN_IN_PLACEHOLDER,
    sign_in_url,
    strip_sign_in_placeholder,
    whatsapp_markup,
)
from main_worker.ports import AgentRuntime, ChannelStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnResult:
    reply: str
    window_open: bool
    # Set when the agent asked for a sign-in; it is sent as a button, not in ``reply``.
    sign_in_url: str | None = None


class Conversation:
    def __init__(
        self,
        *,
        store: ChannelStore,
        agent: AgentRuntime,
        signer: TokenSigner,
        policy: Policy,
        clock: Clock,
    ) -> None:
        self._store = store
        self._agent = agent
        self._signer = signer
        self._policy = policy
        self._clock = clock

    async def identify(self, wa_id: str) -> Identity:
        customer_id = await self._store.linked_customer(wa_id)
        last_sign_in = await self._store.last_sign_in(customer_id) if customer_id else None
        return Identity(
            wa_id=wa_id,
            customer_id=customer_id,
            auth_fresh=self._policy.is_auth_fresh(last_sign_in, self._clock()),
        )

    async def run_turn(
        self,
        identity: Identity,
        message: str,
        *,
        customer_inbound: bool,
        new_receipt_ref: str | None = None,
    ) -> TurnResult:
        """Run one agent turn; an empty ``reply`` means the turn failed or said nothing.

        Session and state errors propagate (Pub/Sub retries them before any model
        call). A failing turn does not: it is logged and reported as an empty reply,
        so callers answer with a fixed fallback instead of paying for the model again.
        """
        pointer = await self._open_session(identity, customer_inbound, new_receipt_ref)
        url = None
        try:
            raw = await self._agent.run_turn(identity.wa_id, pointer.session_id, message)
            url = await self._issue_sign_in(identity, pointer.session_id, raw)
            reply = whatsapp_markup(strip_sign_in_placeholder(raw))
        except Exception as exc:  # Not BaseException: cancellation still propagates.
            logger.exception(
                "agent turn failed",
                extra={
                    "session_id": pointer.session_id,
                    "customer_inbound": customer_inbound,
                    "error_type": type(exc).__name__,
                },
            )
            reply, url = "", None
        else:
            if not reply and not url:
                logger.error(
                    "agent turn returned no text",
                    extra={"session_id": pointer.session_id, "customer_inbound": customer_inbound},
                )
        return TurnResult(
            reply=reply,
            window_open=window_open(pointer.last_inbound_at, self._clock()),
            sign_in_url=url,
        )

    async def _open_session(
        self, identity: Identity, customer_inbound: bool, new_receipt_ref: str | None
    ) -> SessionPointer:
        """Reuse or rotate the session and write the per-turn state into it."""
        now = self._clock()
        previous = await self._store.session_pointer(identity.wa_id)
        rotate = previous is None or self._policy.session_expired(previous.last_activity, now)
        receipt_ref = new_receipt_ref or (None if rotate else previous.last_receipt_ref)

        state = await self._turn_state(identity, receipt_ref)
        session_id = None if rotate else previous.session_id
        if session_id is not None:
            try:
                await self._agent.update_state(identity.wa_id, session_id, state)
            except SessionNotFound:
                logger.warning("agent session vanished; starting a new one")
                session_id = None
        if session_id is None:
            session_id = await self._agent.create_session(identity.wa_id, state)

        pointer = SessionPointer(
            session_id=session_id,
            last_activity=now,
            last_inbound_at=now if customer_inbound else _last_inbound(previous),
            last_receipt_ref=receipt_ref,
        )
        await self._store.save_session_pointer(identity.wa_id, pointer)
        return pointer

    async def _turn_state(self, identity: Identity, receipt_ref: str | None) -> dict:
        token = await asyncio.to_thread(
            issue_turn_token,
            self._signer,
            customer_id=identity.customer_id,
            wa_id=identity.wa_id,
            auth_fresh=identity.auth_fresh,
            last_receipt_ref=receipt_ref,
        )
        return {
            "wa_id": identity.wa_id,
            "customer_id": identity.customer_id,
            "is_linked": identity.is_linked,
            "auth_fresh": identity.auth_fresh,
            "turn_token": token,
        }

    async def _issue_sign_in(self, identity: Identity, session_id: str, reply: str) -> str | None:
        """The one-time sign-in URL when the agent requested a sign-in this turn."""
        state = await self._agent.get_state(identity.wa_id, session_id)
        if not state.get("sign_in_requested"):
            if SIGN_IN_PLACEHOLDER in reply:
                logger.warning("agent wrote the sign-in placeholder without requesting a sign-in")
            return None

        purpose = "reauth" if identity.is_linked else "link"
        token, jti = await asyncio.to_thread(
            issue_link_token, self._signer, wa_id=identity.wa_id, purpose=purpose
        )
        await self._store.save_link_token(
            hashlib.sha256(jti.encode()).hexdigest(),
            wa_id=identity.wa_id,
            purpose=purpose,
            expires_at=self._clock() + timedelta(seconds=LINK_TOKEN_TTL_SECONDS),
        )
        await self._agent.update_state(identity.wa_id, session_id, {"sign_in_requested": False})
        logger.info("issued sign-in link", extra={"purpose": purpose})
        return sign_in_url(self._policy.link_web_url, token)


def _last_inbound(pointer: SessionPointer | None) -> datetime | None:
    return pointer.last_inbound_at if pointer else None
