from types import MappingProxyType, SimpleNamespace

from shop_agent.mcp_headers import audience_for, make_header_provider


def _context(state: dict) -> SimpleNamespace:
    return SimpleNamespace(state=MappingProxyType(state))


async def test_builds_iam_and_turn_token_headers():
    requested_audiences: list[str] = []

    def fake_fetch(audience: str) -> str:
        requested_audiences.append(audience)
        return "id-token-123"

    provider = make_header_provider("https://mcp-shop.example.run.app", fake_fetch)

    headers = await provider(_context({"turn_token": "turn-abc", "wa_id": "5490000000000"}))

    assert headers == {"Authorization": "Bearer id-token-123", "X-Turn-Token": "turn-abc"}
    assert requested_audiences == ["https://mcp-shop.example.run.app"]


async def test_omits_turn_token_header_when_state_has_none():
    provider = make_header_provider("https://aud", lambda _aud: "id-token")

    headers = await provider(_context({}))

    assert headers == {"Authorization": "Bearer id-token"}


def test_audience_is_service_base_url():
    assert audience_for("https://mcp-shop-xyz.a.run.app/mcp") == "https://mcp-shop-xyz.a.run.app"
