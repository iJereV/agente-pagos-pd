"""Deploys the shop agent to Agent Runtime (Vertex AI Agent Engine).

Configuration comes from the environment (the same variables CI sets):

    GOOGLE_CLOUD_PROJECT    project id
    GOOGLE_CLOUD_LOCATION   region, default us-central1
    MCP_SHOP_URL            https://<mcp-shop>/mcp, passed to the deployed agent
    AGENT_MODEL             optional, default gemini-3.5-flash
    AGENT_MODEL_LOCATION    optional, default global (where the model is served)
    MCP_TIMEOUT_SECONDS     optional, default 30 (MCP session setup, covers cold starts)
    AGENT_SERVICE_ACCOUNT   sa-agent email; the agent runs as this identity
    AGENT_STAGING_BUCKET    gs://... bucket where the SDK stages the build
    AGENT_RESOURCE_NAME     optional; when set, that resource is updated in place

    uv run python agent/deploy.py

The last line of stdout is the resource name `projects/.../reasoningEngines/...`.
"""

import os
from pathlib import Path

import cloudpickle
import pydantic
import vertexai
from vertexai.agent_engines import AdkApp

AGENT_DIR = Path(__file__).resolve().parent
PACKAGE = "shop_agent"
# Defaults for the variables the deployed agent reads at import time.
AGENT_ENV_DEFAULTS = {
    "AGENT_MODEL": "gemini-3.5-flash",
    "AGENT_MODEL_LOCATION": "global",
    "MCP_TIMEOUT_SECONDS": "30",
}
REQUIREMENTS = [
    "google-cloud-aiplatform[agent_engines,adk]>=2.10",
    "google-adk[mcp]>=2.15",
    "google-auth[requests]>=2.40",
    # The agent is pickled locally and unpickled remotely: pin the same versions.
    f"cloudpickle=={cloudpickle.__version__}",
    f"pydantic=={pydantic.VERSION}",
]


def main() -> None:
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    resource_name = os.environ.get("AGENT_RESOURCE_NAME")
    # The deployed agent reads these at import time; the local import below needs them too.
    for name, default in AGENT_ENV_DEFAULTS.items():
        os.environ.setdefault(name, default)
    env_vars = {name: os.environ[name] for name in ("MCP_SHOP_URL", *AGENT_ENV_DEFAULTS)}

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
