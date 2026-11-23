"""Entry point: `python -m mcp_shop` serves the MCP app on `$PORT`."""

import uvicorn

from mcp_shop.bootstrap import build_shop
from mcp_shop.config import Settings
from mcp_shop.logs import configure_json_logging
from mcp_shop.server import build_app


def main() -> None:
    configure_json_logging()
    settings = Settings.from_env()
    uvicorn.run(
        build_app(build_shop(settings)), host="0.0.0.0", port=settings.port, log_config=None
    )


if __name__ == "__main__":
    main()
