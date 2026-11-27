import pytest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from shop_agent.agent import root_agent
from shop_agent.output_guard import cut_at_control_token, strip_control_tokens

LEAKED = (
    "Enviá el comprobante y lo verificamos.<|end|><|start|>assistant<|channel|>analysis"
    "<|message|>The assistant responded correctly."
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (LEAKED, "Enviá el comprobante y lo verificamos."),
        ("<|channel|>final<|message|>Hola", ""),
        ("Sin tokens. Precio: $5 <3", "Sin tokens. Precio: $5 <3"),
    ],
)
def test_text_is_cut_at_the_first_control_token(text: str, expected: str) -> None:
    assert cut_at_control_token(text) == expected


def test_callback_cleans_leaked_parts_and_keeps_the_rest() -> None:
    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=LEAKED), types.Part(text="Otra parte.")],
        )
    )

    cleaned = strip_control_tokens(None, response)

    assert cleaned is response
    assert [p.text for p in cleaned.content.parts] == [
        "Enviá el comprobante y lo verificamos.",
        "Otra parte.",
    ]


def test_callback_leaves_clean_responses_alone() -> None:
    response = LlmResponse(content=types.Content(role="model", parts=[types.Part(text="Hola")]))
    assert strip_control_tokens(None, response) is None
    assert strip_control_tokens(None, LlmResponse()) is None


def test_agent_runs_the_guard_after_every_model_call() -> None:
    assert root_agent.after_model_callback is strip_control_tokens
