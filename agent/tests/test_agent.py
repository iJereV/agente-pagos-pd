from google.adk.models import Gemini
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from shop_agent.agent import MCP_TIMEOUT_SECONDS, root_agent, shop_tools
from shop_agent.instruction import INSTRUCTION, SIGN_IN_PLACEHOLDER


def test_root_agent_wires_local_tools_and_mcp_toolset():
    tool_names = {getattr(tool, "__name__", None) for tool in root_agent.tools}
    toolsets = [tool for tool in root_agent.tools if isinstance(tool, McpToolset)]

    assert {"get_catalog", "request_sign_in"} <= tool_names
    assert len(toolsets) == 1
    assert toolsets[0].header_provider is not None


async def test_instruction_bypasses_state_injection_and_keeps_placeholder():
    instruction, bypass_state_injection = await root_agent.canonical_instruction(ctx=None)

    assert bypass_state_injection is True
    assert instruction == INSTRUCTION
    assert "{{SIGN_IN_LINK}}" == SIGN_IN_PLACEHOLDER
    assert SIGN_IN_PLACEHOLDER in instruction


def test_model_is_served_from_its_own_location_not_the_runtime_region(monkeypatch):
    # Agent Runtime sets GOOGLE_CLOUD_LOCATION to the region the agent runs in.
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    model = root_agent.model
    assert isinstance(model, Gemini)
    assert model.model == "gemini-3.5-flash"
    client = model.api_client
    assert client.vertexai is True
    assert client._api_client.location == "global"


def test_mcp_session_timeout_covers_a_cold_start():
    assert MCP_TIMEOUT_SECONDS == 30
    assert shop_tools._connection_params.timeout == 30
