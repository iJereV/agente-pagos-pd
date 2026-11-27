"""Closed tool outcomes, shaped exactly as in docs/contracts.md."""

from typing import Literal

from pydantic import BaseModel


class Rejected(BaseModel):
    """An outcome that carries only its status."""

    status: Literal[
        "auth_required",
        "not_linked",
        "invalid_items",
        "no_receipt",
        "not_a_receipt",
        "already_used",
        "not_found_yet",
        "manual_review",
        "not_found",
    ]


class Balance(BaseModel):
    status: Literal["ok"] = "ok"
    balance_cents: int
    welcome_credit_cents: int = 0
    """Welcome credit granted by this call (a new customer's first one); 0 otherwise."""


class OrderCreated(BaseModel):
    status: Literal["created"] = "created"
    order_id: str
    total_cents: int
    balance_cents: int
    """Balance after the order was debited."""
    welcome_credit_cents: int = 0
    """Welcome credit granted by this call (a new customer's first one); 0 otherwise."""


class NotEnoughBalance(BaseModel):
    status: Literal["insufficient_balance"] = "insufficient_balance"
    balance_cents: int
    total_cents: int
    payment_needed_cents: int
    """`total_cents - balance_cents`, computed here so the model never does arithmetic."""
    welcome_credit_cents: int = 0
    """Welcome credit granted by this call (a new customer's first one); 0 otherwise."""


class Credited(BaseModel):
    status: Literal["credited"] = "credited"
    amount_cents: int
    balance_cents: int
    """Balance after the transfer was credited."""
    welcome_credit_cents: int = 0
    """Welcome credit granted by this call (a new customer's first one); 0 otherwise."""


class OrderStatusView(BaseModel):
    status: Literal["ok"] = "ok"
    order_status: Literal["unpaid", "partially_paid", "paid"]
    total_cents: int
    paid_cents: int


AUTH_REQUIRED = Rejected(status="auth_required")
NOT_LINKED = Rejected(status="not_linked")
