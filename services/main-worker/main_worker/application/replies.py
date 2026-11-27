"""Sends an agent reply: plain text, or text with the sign-in button under it."""

from main_worker.domain.rendering import (
    BUTTON_BODY_MAX_CHARS,
    SIGN_IN_BUTTON_BODY,
    SIGN_IN_BUTTON_LABEL,
)
from main_worker.ports import WhatsApp


async def send_reply(whatsapp: WhatsApp, to: str, text: str, sign_in_url: str | None) -> None:
    """One message when the text fits a button body; otherwise the text, then the button."""
    if sign_in_url is None:
        await whatsapp.send_text(to, text)
        return
    if text and len(text) <= BUTTON_BODY_MAX_CHARS:
        await whatsapp.send_link_button(to, text, SIGN_IN_BUTTON_LABEL, sign_in_url)
        return
    if text:
        await whatsapp.send_text(to, text)
    await whatsapp.send_link_button(to, SIGN_IN_BUTTON_BODY, SIGN_IN_BUTTON_LABEL, sign_in_url)
