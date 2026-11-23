"""Local agent tools. They touch no data or money, so they live inside the agent."""

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


def request_sign_in(tool_context: ToolContext) -> dict[str, bool]:
    """Requests a Google sign-in link for the customer.

    Call it when a shop tool answers auth_required or not_linked, then write
    {{SIGN_IN_LINK}} in the reply where the link should appear.
    """
    tool_context.state[SIGN_IN_REQUESTED_KEY] = True
    return {"requested": True}
