"""Local agent tools. They touch no data or money, so they live inside the agent."""

import os
from typing import Any

from google.adk.tools.tool_context import ToolContext

# Mirrors the catalog in docs/contracts.md. mcp-shop prices orders from its own copy.
CATALOG_CENTS: dict[str, int] = {"dog": 100, "penguin": 300, "capybara": 500}

SIGN_IN_REQUESTED_KEY = "sign_in_requested"


def format_pesos(cents: int) -> str:
    """Formats integer cents as Argentine pesos, e.g. 100 -> "$1", 150 -> "$1,50"."""
    pesos, remainder = divmod(cents, 100)
    return f"${pesos}" if remainder == 0 else f"${pesos},{remainder:02d}"


def get_catalog() -> dict[str, Any]:
    """Returns the image catalog with the price of each animal.

    Use it whenever the customer asks what can be ordered or how much something costs.
    """
    return {
        "currency": "ARS",
        "items": [
            {"animal": animal, "price_cents": cents, "price": format_pesos(cents)}
            for animal, cents in CATALOG_CENTS.items()
        ],
    }


# Where customers transfer to. Configured per deployment, never hard-coded: the
# repository is public and the agent must only repeat these exact values.
PAYMENT_ENV = {"alias": "PAYMENT_ALIAS", "cvu": "PAYMENT_CVU", "holder": "PAYMENT_HOLDER"}


def get_payment_details() -> dict[str, Any]:
    """Returns the account where customers pay by bank transfer (alias, CVU, holder).

    Use it whenever the customer asks how or where to pay. Give only the fields it
    returns, copied exactly.
    """
    details = {
        field: value
        for field, name in PAYMENT_ENV.items()
        if (value := os.environ.get(name, "").strip())
    }
    if "alias" not in details and "cvu" not in details:
        return {"available": False}
    return {"available": True, **details}


def request_sign_in(tool_context: ToolContext) -> dict[str, bool]:
    """Requests a Google sign-in link for the customer.

    Call it when a shop tool answers auth_required or not_linked, then write
    {{SIGN_IN_LINK}} in the reply where the link should appear.
    """
    tool_context.state[SIGN_IN_REQUESTED_KEY] = True
    return {"requested": True}
