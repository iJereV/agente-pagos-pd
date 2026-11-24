"""Split a Meta webhook payload into ``customer_message`` events (docs/contracts.md)."""

from datetime import UTC, datetime
from typing import Any

_MEDIA_TYPES = ("image", "document")


def extract_customer_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """One event per message in ``entry[].changes[].value.messages[]``.

    Delivery ``statuses`` and any other change types are ignored.
    """
    events = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = _profile_names(value)
            for message in value.get("messages") or []:
                events.append(_to_event(message, names))
    return events


def failed_deliveries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Errors from ``failed`` delivery statuses, without the recipient's number.

    Meta accepts a send synchronously and reports some failures only here.
    """
    failures = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            for status in (change.get("value") or {}).get("statuses") or []:
                if status.get("status") != "failed":
                    continue
                for error in status.get("errors") or [{}]:
                    failures.append(
                        {
                            "wamid": status.get("id"),
                            "error_code": error.get("code"),
                            "error_title": error.get("title"),
                            "error_details": (error.get("error_data") or {}).get("details"),
                        }
                    )
    return failures


def _profile_names(value: dict[str, Any]) -> dict[str, str]:
    return {
        contact["wa_id"]: (contact.get("profile") or {}).get("name")
        for contact in value.get("contacts") or []
        if "wa_id" in contact
    }


def _to_event(message: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    kind = message.get("type")
    message_type = kind if kind in ("text", *_MEDIA_TYPES) else "other"
    media = (message.get(kind) or {}) if message_type in _MEDIA_TYPES else {}
    text = (message.get("text") or {}).get("body") if kind == "text" else media.get("caption")
    wa_id = message["from"]
    return {
        "type": "customer_message",
        "wamid": message["id"],
        "wa_id": wa_id,
        "timestamp": _iso_utc(message.get("timestamp")),
        "message_type": message_type,
        "text": text,
        "media_id": media.get("id"),
        "mime_type": media.get("mime_type"),
        "profile_name": names.get(wa_id),
    }


def _iso_utc(unix_seconds: str | None) -> str:
    moment = datetime.fromtimestamp(int(unix_seconds), UTC) if unix_seconds else datetime.now(UTC)
    return moment.isoformat().replace("+00:00", "Z")
