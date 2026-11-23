"""ADK shop agent: local catalog and sign-in tools plus the mcp-shop domain tools."""

import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from .instruction import shop_instruction
from .mcp_headers import audience_for, make_header_provider
from .tools import get_catalog, request_sign_in

AGENT_MODEL = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")
MCP_SHOP_URL = os.environ["MCP_SHOP_URL"]

shop_tools = McpToolset(
    connection_params=StreamableHTTPConnectionParams(url=MCP_SHOP_URL),
    tool_filter=["get_balance", "create_order", "verify_receipt", "get_order_status"],
    header_provider=make_header_provider(audience_for(MCP_SHOP_URL)),
)

root_agent = Agent(
    name="shop_agent",
    model=AGENT_MODEL,
    description="WhatsApp assistant of a shop selling AI-generated animal images on credit.",
    instruction=shop_instruction,
    tools=[get_catalog, request_sign_in, shop_tools],
)
