"""GrokProvider unit tests. httpx is mocked via MockTransport; nothing touches the network."""

import asyncio
import json

import httpx
import pytest

from app.api.deps import get_provider
from app.main import app
from app.models import Game, Platform
from app.providers import GrokProvider, ImageInput, ProviderError
from app.services.budget import start_of_local_day

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _game() -> Game:
    return Game(
        name="Ash Protocol",
        pitch="Turn-based squad tactics in a nuclear wasteland",
        genres=["turn-based tactics"],
        platforms=[Platform.PC],
        comparable_games=["Wasteland 3", "Fallout Tactics"],
        languages=["en", "ja"],
    )


def _response(profile: dict, ticks: int = 31_000_000) -> dict:
    return {
        "id": "resp_1",
        "model": "grok-4.3",
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(profile)}]},
        ],
        "usage": {"input_tokens": 900, "output_tokens": 700, "cost_in_usd_ticks": ticks},
    }


PROFILE = {
    "themes": ["squad survival", "squad survival", "scavenging"],
    "keywords_by_language": {"en": ["xcom-like", "wasteland tactics"], "ja": ["ターン制ストラテジー"]},
    "suggested_comparables": [
        {"name": "Wasteland 3", "reason": "user listed it"},
        {"name": "Phoenix Point", "reason": "XCOM-style squad tactics"},
    ],
    "visual_style": ["gritty", "isometric"],
    "target_audience": "PC tactics fans.",
}


def _provider(handler) -> GrokProvider:
    return GrokProvider("test-key", "https://api.x.test/v1", "grok-4.3", transport=httpx.MockTransport(handler))


def test_generate_profile_request_and_mapping(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(PNG)
    webp = tmp_path / "b.webp"
    webp.write_bytes(b"RIFF0000WEBP")
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_response(PROFILE))

    game = _game()
    profile = asyncio.run(
        _provider(handler).generate_profile(game, [ImageInput(img, "image/png"), ImageInput(webp, "image/webp")])
    )

    body = seen["body"]
    assert seen["url"] == "https://api.x.test/v1/responses"
    assert seen["auth"] == "Bearer test-key"
    assert body["model"] == "grok-4.3" and body["store"] is False and "tools" not in body
    fmt = body["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True
    assert fmt["schema"]["properties"]["keywords_by_language"]["required"] == ["en", "ja"]
    content = body["input"][0]["content"]
    images = [c for c in content if c["type"] == "input_image"]
    assert len(images) == 1 and images[0]["image_url"].startswith("data:image/png;base64,")
    assert "Wasteland 3" in content[0]["text"] and "1 unsupported" in content[0]["text"]

    assert profile.model == "grok-4.3" and profile.generated_by == "grok"
    assert profile.cost_usd == pytest.approx(0.0031)
    assert profile.themes == ["squad survival", "scavenging"]
    assert [c.name for c in profile.suggested_comparables] == ["Phoenix Point"]
    assert profile.keywords_by_language == {"en": ["xcom-like", "wasteland tactics"], "ja": ["ターン制ストラテジー"]}


@pytest.mark.parametrize(
    "handler, msg",
    [
        (lambda r: httpx.Response(401, json={"error": "Incorrect API key"}), "401"),
        (lambda r: httpx.Response(503, text="upstream down"), "503"),
        (lambda r: httpx.Response(200, json=_response({"themes": "nope"})), "validation"),
    ],
)
def test_generate_profile_errors(handler, msg):
    with pytest.raises(ProviderError, match=msg):
        asyncio.run(_provider(handler).generate_profile(_game(), []))


def test_generate_profile_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError, match="timed out"):
        asyncio.run(_provider(handler).generate_profile(_game(), []))


def test_route_maps_provider_error_to_502(client, game):
    app.dependency_overrides[get_provider] = lambda: _provider(lambda r: httpx.Response(500, json={"error": "boom"}))
    r = client.post(f"/api/v1/games/{game['id']}/profile/generate")
    assert r.status_code == 502 and "500" in r.json()["detail"]


def test_route_budget_guard(client, game, settings, repo):
    settings.daily_budget_usd = 0.005
    app.dependency_overrides[get_provider] = lambda: _provider(lambda r: httpx.Response(200, json=_response(PROFILE)))
    first = client.post(f"/api/v1/games/{game['id']}/profile/generate")
    assert first.status_code == 200
    assert first.json()["cost_usd"] == pytest.approx(0.0031) and first.json()["model"] == "grok-4.3"
    assert client.post(f"/api/v1/games/{game['id']}/profile/generate").status_code == 200  # 0.0031 < 0.005
    third = client.post(f"/api/v1/games/{game['id']}/profile/generate")
    assert third.status_code == 429 and "budget" in third.json()["detail"]
    assert repo.usage_cost_since(start_of_local_day()) == pytest.approx(0.0062)  # ledger persisted both calls


def test_prompt_includes_seed_keywords_and_key_art(tmp_path):
    seen: dict = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_response(PROFILE))

    art = tmp_path / "art.png"
    art.write_bytes(PNG)
    game = _game()
    game.seed_keywords = {"ja": ["戦術SLG"]}
    asyncio.run(_provider(handler).generate_profile(game, [ImageInput(art, "image/png", kind="key_art")]))
    text = seen["body"]["input"][0]["content"][0]["text"]
    assert "SEED KEYWORDS" in text and "ja: 戦術SLG" in text and "first 1 key art" in text
