"""Time-based rules: auth freshness, session rotation and the 24 h WhatsApp window."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from shared.config import env_int, env_str

CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class Policy:
    link_web_url: str
    session_idle: timedelta = timedelta(hours=24)
    auth_fresh_for: timedelta = timedelta(hours=24)
    order_ready_template: str = "hello_world"
    template_language: str = "en_US"

    @classmethod
    def from_env(cls) -> "Policy":
        return cls(
            link_web_url=env_str("LINK_WEB_URL"),
            session_idle=timedelta(hours=env_int("SESSION_IDLE_HOURS", 24)),
            auth_fresh_for=timedelta(hours=env_int("AUTH_FRESH_HOURS", 24)),
            order_ready_template=env_str("WA_ORDER_READY_TEMPLATE", "hello_world"),
            template_language=env_str("WA_TEMPLATE_LANG", "en_US"),
        )

    def is_auth_fresh(self, last_sign_in_at: datetime | None, now: datetime) -> bool:
        return last_sign_in_at is not None and now - last_sign_in_at <= self.auth_fresh_for

    def session_expired(self, last_activity: datetime, now: datetime) -> bool:
        return now - last_activity > self.session_idle


def window_open(last_inbound_at: datetime | None, now: datetime) -> bool:
    """Free-form messages are allowed for 24 h after the customer's last message."""
    return last_inbound_at is not None and now - last_inbound_at < CUSTOMER_SERVICE_WINDOW
