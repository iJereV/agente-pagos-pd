import os

# shop_agent.agent reads its configuration at import time.
os.environ.setdefault("MCP_SHOP_URL", "https://mcp-shop.example.run.app/mcp")
