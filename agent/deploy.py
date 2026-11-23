"""Deploys the shop agent to Agent Runtime (Vertex AI Agent Engine).

Configuration comes from the environment (the same variables CI sets):

    GOOGLE_CLOUD_PROJECT    project id
    GOOGLE_CLOUD_LOCATION   region, default us-central1
    MCP_SHOP_URL            https://<mcp-shop>/mcp, passed to the deployed agent
    AGENT_MODEL             optional, default gemini-2.5-flash
    AGENT_SERVICE_ACCOUNT   sa-agent email; the agent runs as this identity
    AGENT_STAGING_BUCKET    gs://... bucket where the SDK stages the build
    AGENT_RESOURCE_NAME     optional; when set, that resource is updated in place

    uv run python agent/deploy.py

The last line of stdout is the resource name `projects/.../reasoningEngines/...`.
"""

import os
from pathlib import Path

import vertexai
from vertexai.agent_engines import AdkApp

AGENT_DIR = Path(__file__).resolve().parent
PACKAGE = "shop_agent"
DEFAULT_MODEL = "gemini-2.5-flash"
REQUIREMENTS = [
    "google-cloud-aiplatform[agent_engines,adk]>=2.10",
    "google-adk[mcp]>=2.15",
    "google-auth[requests]>=2.40",
]


def main() -> None:
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    resource_name = os.environ.get("AGENT_RESOURCE_NAME")
    # The deployed agent reads these at import time; the local import below needs them too.
    os.environ.setdefault("AGENT_MODEL", DEFAULT_MODEL)
    env_vars = {name: os.environ[name] for name in ("MCP_SHOP_URL", "AGENT_MODEL")}

    # extra_packages are archived relative to the working directory.
    os.chdir(AGENT_DIR)
    from shop_agent.agent import root_agent

    config = {
        "display_name": "shop-agent",
        "staging_bucket": os.environ["AGENT_STAGING_BUCKET"],
        "requirements": REQUIREMENTS,
        "extra_packages": [PACKAGE],
        "env_vars": env_vars,
        "service_account": os.environ["AGENT_SERVICE_ACCOUNT"],
    }
    client = vertexai.Client(project=project, location=location)
    app = AdkApp(agent=root_agent)
    if resource_name:
        remote = client.agent_engines.update(name=resource_name, agent=app, config=config)
    else:
        remote = client.agent_engines.create(agent=app, config=config)
    print(remote.api_resource.name)


if __name__ == "__main__":
    main()
