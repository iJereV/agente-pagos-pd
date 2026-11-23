"""``AgentRuntime`` on Vertex AI Agent Engine (Agent Runtime).

Sessions go through ADK's ``VertexAiSessionService`` (initial state on create, state
deltas as appended events). Turns go through the deployed ``AdkApp``'s
``async_stream_query``, whose events are ADK events serialised as dicts.
"""

import asyncio
import time
import uuid
from typing import Any

import vertexai
from google.adk.events import Event, EventActions
from google.adk.sessions import Session, VertexAiSessionService

from main_worker.domain.errors import SessionNotFound

_STATE_AUTHOR = "main-worker"


class VertexAgentRuntime:
    def __init__(self, *, resource_name: str, project: str, location: str) -> None:
        self._resource_name = resource_name
        self._sessions = VertexAiSessionService(
            project=project, location=location, agent_engine_id=resource_name.rsplit("/", 1)[-1]
        )
        self._client = vertexai.Client(project=project, location=location)
        self._engine: Any = None

    async def create_session(self, user_id: str, state: dict[str, Any]) -> str:
        session = await self._sessions.create_session(
            app_name=self._resource_name, user_id=user_id, state=state
        )
        return session.id

    async def update_state(self, user_id: str, session_id: str, delta: dict[str, Any]) -> None:
        session = await self._session(user_id, session_id)
        event = Event(
            invocation_id=f"state-{uuid.uuid4()}",
            author=_STATE_AUTHOR,
            actions=EventActions(state_delta=delta),
            timestamp=time.time(),
        )
        await self._sessions.append_event(session, event)

    async def get_state(self, user_id: str, session_id: str) -> dict[str, Any]:
        return dict((await self._session(user_id, session_id)).state)

    async def run_turn(self, user_id: str, session_id: str, message: str) -> str:
        engine = await self._remote_engine()
        reply = ""
        async for event in engine.async_stream_query(
            user_id=user_id, session_id=session_id, message=message
        ):
            text = _final_text(event)
            if text:
                reply = text
        return reply.strip()

    async def _session(self, user_id: str, session_id: str) -> Session:
        session = await self._sessions.get_session(
            app_name=self._resource_name, user_id=user_id, session_id=session_id
        )
        if session is None:
            raise SessionNotFound(session_id)
        return session

    async def _remote_engine(self) -> Any:
        if self._engine is None:
            self._engine = await asyncio.to_thread(
                self._client.agent_engines.get, name=self._resource_name
            )
        return self._engine


def _final_text(event: dict[str, Any]) -> str:
    """Text written by the agent in a complete (non-partial) event, without thoughts."""
    if event.get("partial") or event.get("author") == "user":
        return ""
    parts = (event.get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if p.get("text") and not p.get("thought"))
