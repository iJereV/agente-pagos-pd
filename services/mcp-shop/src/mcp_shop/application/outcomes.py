"""Closed tool outcomes, shaped exactly as in docs/contracts.md."""

from datetime import datetime
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


class UnpaidOrder(BaseModel):
    order_id: str
    total_cents: int
    paid_cents: int
    created_at: datetime


class Balance(BaseModel):
    status: Literal["ok"] = "ok"
    debt_cents: int
    credit_balance_cents: int
    available_credit_cents: int
    unpaid_orders: list[UnpaidOrder]


class OrderCreated(BaseModel):
    status: Literal["created"] = "created"
    order_id: str
    total_cents: int
    credit_used_cents: int


class CreditLimit(BaseModel):
    status: Literal["credit_limit"] = "credit_limit"
    available_credit_cents: int


class AllocatedAmount(BaseModel):
    order_id: str
    amount_cents: int


class Credited(BaseModel):
    status: Literal["credited"] = "credited"
    amount_cents: int
    allocations: list[AllocatedAmount]
    credit_balance_cents: int
    debt_cents: int


class OrderStatusView(BaseModel):
    status: Literal["ok"] = "ok"
    order_status: Literal["unpaid", "partially_paid", "paid"]
    total_cents: int
    paid_cents: int


AUTH_REQUIRED = Rejected(status="auth_required")
NOT_LINKED = Rejected(status="not_linked")
