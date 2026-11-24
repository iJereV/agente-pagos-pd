"""ADK shop agent: local catalog and sign-in tools plus the mcp-shop domain tools."""

import os

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from .instruction import shop_instruction
from .mcp_headers import audience_for, make_header_provider
from .tools import get_catalog, request_sign_in

AGENT_MODEL = os.environ.get("AGENT_MODEL", "vertex_ai/openai/gpt-oss-120b-maas")
# Where the model is served. Independent of GOOGLE_CLOUD_LOCATION, which is the region
# the agent itself runs in: some models are only served from the `global` endpoint.
AGENT_MODEL_LOCATION = os.environ.get("AGENT_MODEL_LOCATION", "global")
MCP_SHOP_URL = os.environ["MCP_SHOP_URL"]
# mcp-shop scales to zero; a cold start takes several seconds, so ADK's 5 s default
# for establishing the MCP session is too short.
MCP_TIMEOUT_SECONDS = float(os.environ.get("MCP_TIMEOUT_SECONDS", "30"))


def build_model(name: str, location: str) -> Gemini | LiteLlm:
    """Gemini by id, or a Vertex AI open model (MaaS) given as ``vertex_ai/<publisher>/<id>``.

    Open models go through LiteLLM, which reads the project and region from
    VERTEXAI_PROJECT and VERTEXAI_LOCATION.
    """
    if name.startswith("vertex_ai/"):
        os.environ.setdefault("VERTEXAI_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
        os.environ.setdefault("VERTEXAI_LOCATION", location)
        return LiteLlm(model=name)
    return Gemini(model=name, client_kwargs={"vertexai": True, "location": location})


model = build_model(AGENT_MODEL, AGENT_MODEL_LOCATION)

shop_tools = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=MCP_SHOP_URL,
        timeout=MCP_TIMEOUT_SECONDS,
    ),
    tool_filter=["get_balance", "create_order", "verify_receipt", "get_order_status"],
    header_provider=make_header_provider(audience_for(MCP_SHOP_URL)),
)

root_agent = Agent(
    name="shop_agent",
    model=model,
    description="WhatsApp assistant of a shop selling AI-generated animal images on credit.",
    instruction=shop_instruction,
    tools=[get_catalog, request_sign_in, shop_tools],
)
