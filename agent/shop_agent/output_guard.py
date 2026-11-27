"""Drops gpt-oss control tokens that sometimes leak into the reply text.

gpt-oss writes its output as "harmony" messages separated by tokens such as <|end|>,
<|start|>, <|channel|> and <|message|>. When generation does not stop at the end of
the final message, the model keeps going and those tokens, followed by more of its own
analysis, end up in the text. Everything from the first such token on is dropped, before
the response is stored in the session or sent to the customer.
"""

import re

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

_CONTROL_TOKEN = re.compile(r"<\|[a-z_]+\|>")


def cut_at_control_token(text: str) -> str:
    match = _CONTROL_TOKEN.search(text)
    return text if match is None else text[: match.start()].rstrip()


def strip_control_tokens(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> LlmResponse | None:
    """ADK after_model_callback: returns the cleaned response, or None when unchanged."""
    parts = llm_response.content.parts if llm_response.content else None
    leaked = [part for part in parts or [] if part.text and _CONTROL_TOKEN.search(part.text)]
    for part in leaked:
        part.text = cut_at_control_token(part.text)
    return llm_response if leaked else None
