import os

from google.adk.models import Gemini
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from shop_agent.agent import MCP_TIMEOUT_SECONDS, build_model, root_agent, shop_tools
from shop_agent.instruction import INSTRUCTION, SIGN_IN_PLACEHOLDER


def test_root_agent_wires_local_tools_and_mcp_toolset():
    tool_names = {getattr(tool, "__name__", None) for tool in root_agent.tools}
    toolsets = [tool for tool in root_agent.tools if isinstance(tool, McpToolset)]

    assert {"get_catalog", "get_payment_details", "request_sign_in"} <= tool_names
    assert len(toolsets) == 1
    assert toolsets[0].header_provider is not None


async def test_instruction_bypasses_state_injection_and_keeps_placeholder():
    instruction, bypass_state_injection = await root_agent.canonical_instruction(ctx=None)

    assert bypass_state_injection is True
    assert instruction == INSTRUCTION
    assert "{{SIGN_IN_LINK}}" == SIGN_IN_PLACEHOLDER
    assert SIGN_IN_PLACEHOLDER in instruction


def test_gemini_is_served_from_its_own_location_not_the_runtime_region(monkeypatch):
    # Agent Runtime sets GOOGLE_CLOUD_LOCATION to the region the agent runs in.
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    model = build_model("gemini-3.5-flash", "global")
    assert isinstance(model, Gemini)
    client = model.api_client
    assert client.vertexai is True
    assert client._api_client.location == "global"


def test_open_models_go_through_litellm_on_vertex(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.delenv("VERTEXAI_PROJECT", raising=False)
    monkeypatch.delenv("VERTEXAI_LOCATION", raising=False)

    model = build_model("vertex_ai/openai/gpt-oss-120b-maas", "global")
    assert isinstance(model, LiteLlm)
    assert model.model == "vertex_ai/openai/gpt-oss-120b-maas"
    assert os.environ["VERTEXAI_PROJECT"] == "test-project"
    assert os.environ["VERTEXAI_LOCATION"] == "global"


def test_default_model_is_gpt_oss():
    assert isinstance(root_agent.model, LiteLlm)


def test_mcp_session_timeout_covers_a_cold_start():
    assert MCP_TIMEOUT_SECONDS == 30
    assert shop_tools._connection_params.timeout == 30
