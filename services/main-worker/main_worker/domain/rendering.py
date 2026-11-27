"""Text in and out of the agent: turn inputs, the sign-in placeholder, storage paths."""

import json
import mimetypes
import re
from typing import Any
from urllib.parse import quote

from main_worker.domain.models import CustomerMessage

SIGN_IN_PLACEHOLDER = "{{SIGN_IN_LINK}}"

# Fixed customer-facing texts used when the agent turn fails or writes nothing.
TURN_FALLBACK_REPLY = "Perdón, tuve un problema para responderte. Probá de nuevo en un ratito."
ORDER_READY_FALLBACK_CAPTION = "¡Listo! Acá tenés tus imágenes."

# The sign-in link goes out as a WhatsApp call-to-action button (label <= 20 chars).
SIGN_IN_BUTTON_LABEL = "Iniciar sesión"
SIGN_IN_BUTTON_BODY = "Tocá el botón para iniciar sesión con Google."
# WhatsApp's limit for the body text of an interactive message.
BUTTON_BODY_MAX_CHARS = 1024

_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}


def customer_turn_input(message: CustomerMessage) -> str:
    """The customer's text as-is; media is announced, followed by any caption."""
    if message.message_type == "text":
        return message.text or ""
    announcement = {
        "image": "[image received]",
        "document": "[document received]",
    }.get(message.message_type, "[unsupported message received]")
    return f"{announcement} {message.text}" if message.text else announcement


def system_event_input(event: str, **fields: Any) -> str:
    """A single ``SYSTEM_EVENT {...}`` line the agent recognises as a system event."""
    body = json.dumps({"event": event, **fields}, ensure_ascii=False, separators=(",", ":"))
    return f"SYSTEM_EVENT {body}"


def sign_in_url(link_web_url: str, token: str) -> str:
    return f"{link_web_url.rstrip('/')}/link?t={quote(token, safe='')}"


def strip_sign_in_placeholder(reply: str) -> str:
    """Remove the placeholder: the sign-in link travels as a button, never as text."""
    text = reply.replace(SIGN_IN_PLACEHOLDER, "")
    lines = (re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def whatsapp_markup(text: str) -> str:
    """Markdown bold (``**x**`` or ``__x__``) as WhatsApp bold (``*x*``).

    Models slip into Markdown despite the instruction; WhatsApp shows double asterisks
    literally.
    """
    return re.sub(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", r"*\2*", text)


def receipt_path(owner_id: str, wamid: str, mime_type: str) -> str:
    """``receipts/{customer_id or wa_id}/{wamid}.{ext}``."""
    return f"receipts/{owner_id}/{wamid}.{file_extension(mime_type)}"


def file_extension(mime_type: str) -> str:
    base = mime_type.split(";")[0].strip().lower()
    if base in _EXTENSIONS:
        return _EXTENSIONS[base]
    guessed = mimetypes.guess_extension(base)
    return guessed.lstrip(".") if guessed else "bin"


def content_type_for(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"
