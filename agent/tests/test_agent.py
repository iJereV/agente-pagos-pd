from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from shop_agent.agent import root_agent
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
