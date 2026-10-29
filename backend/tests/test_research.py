import json

import httpx
import pytest

from app.api.deps import get_collector
from app.main import app
from app.models import Game
from app.providers.base import CreatorCandidate, ResearchPostInput
from app.providers.grok import GrokProvider
from app.services.research_service import comparable_query, plan_queries, reject_reason
from app.x import FakeXClient, XApiCollector, XApiError
from app.x.client import parse_search_response


@pytest.fixture
def nk(client):
    r = client.post(
        "/api/v1/games",
        json={
            "name": "Nuclear Knights",
            "comparable_games": ["Fallout 2", "XCOM"],
            "keywords": ["tactical rpg"],
            "seed_keywords": {"en": ["turn-based tactics"], "ja": ["ターン制"]},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_query_building():
    q = comparable_query("Fallout 2", "ja")
    assert q.startswith('"Fallout 2" lang:ja') and "-is:retweet" in q and "-sale" in q and len(q) <= 512
    g = Game(name="NK", comparable_games=["XCOM", "Wartales"], keywords=["tactics"])
    qs = plan_queries(g)
    assert {p[0] for p in qs} >= {"XCOM", "Wartales"}
    assert all(len(p[2]) <= 512 for p in qs)


@pytest.mark.parametrize(
    "text,spam",
    [
        ("XCOM 2 is 75% off today https://t.co/x", True),
        ("Huge SALE on Wartales!", True),
        ("https://t.co/abc #XCOM", True),
        ("Fallout 2 still has the best writing of any RPG, nothing comes close", False),
    ],
)
def test_spam_filter(text, spam):
    assert (reject_reason(text) is not None) is spam


def test_parse_search_response():
    page = parse_search_response(
        {
            "data": [
                {
                    "id": "1",
                    "text": "hi",
                    "author_id": "9",
                    "created_at": "2026-10-01T00:00:00Z",
                    "lang": "en",
                    "public_metrics": {"like_count": 3},
                }
            ],
            "includes": {
                "users": [{"id": "9", "username": "bob", "name": "Bob", "public_metrics": {"followers_count": 1234}}]
            },
            "meta": {"result_count": 1},
        }
    )
    assert page.posts[0].likes == 3 and page.users["9"].followers == 1234


def test_estimate_and_run_flow(client, nk, repo):
    gid = nk["id"]
    est = client.get(f"/api/v1/games/{gid}/research/estimate", params={"max_posts_total": 40}).json()
    assert est["max_posts_total"] == 40 and est["max_total_cost_usd"] == pytest.approx(0.3)
    assert est["x_source"] == "fake" and est["can_run"]

    r = client.post(f"/api/v1/games/{gid}/research", json={"max_posts_per_comparable": 10, "max_posts_total": 15})
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "completed"
    assert 0 < run["post_count"] <= 15
    assert sum(run["stats"]["filtered"].values()) > 0
    assert run["brief"]["summary"]
    assert run["x_cost_usd"] == pytest.approx(run["post_count"] * 0.005, abs=0.06)
    # every referenced post id resolves to a stored post
    for ph in run["brief"]["player_phrasing"]:
        assert set(ph["example_post_ids"]) <= set(run["posts"])
    for c in run["brief"]["creators"]:
        assert c["followers"] >= 500

    listed = client.get(f"/api/v1/games/{gid}/research").json()
    assert [x["id"] for x in listed] == [run["id"]]
    got = client.get(f"/api/v1/research/{run['id']}").json()
    assert got["brief"] == run["brief"]
    assert client.get("/api/v1/research/nope").status_code == 404
    assert len(repo.list_research_posts(run["id"])) == run["post_count"]
    # ledger has X reads recorded
    from datetime import UTC, datetime, timedelta

    assert repo.usage_cost_since(datetime.now(UTC) - timedelta(hours=1)) >= run["x_cost_usd"]

    # deleting the game cascades
    assert client.delete(f"/api/v1/games/{gid}").status_code == 204
    assert client.get(f"/api/v1/research/{run['id']}").status_code == 404


def test_per_comparable_cap(client, nk):
    fake = FakeXClient(posts_per_query=30)
    app.dependency_overrides[get_collector] = lambda: XApiCollector(fake)
    run = client.post(
        f"/api/v1/games/{nk['id']}/research", json={"max_posts_per_comparable": 10, "max_posts_total": 100}
    ).json()
    assert run["stats"]["by_comparable"]["XCOM"] <= 10 and run["stats"]["by_comparable"]["Fallout 2"] <= 10


def test_budget_preflight_rejects(client, nk, settings):
    settings.daily_budget_usd = 0.2
    r = client.post(f"/api/v1/games/{nk['id']}/research", json={"max_posts_total": 400})
    assert r.status_code == 429
    assert client.get(f"/api/v1/games/{nk['id']}/research").json() == []


def test_requires_comparables(client, game):
    assert client.post(f"/api/v1/games/{game['id']}/research").status_code == 422


def test_x_error_marks_failed(client, nk):
    class Boom(FakeXClient):
        async def search_recent(self, *a, **k):
            raise XApiError("403 client-not-enrolled", status_code=403)

    app.dependency_overrides[get_collector] = lambda: XApiCollector(Boom())
    run = client.post(f"/api/v1/games/{nk['id']}/research", json={"max_posts_total": 50}).json()
    assert run["status"] == "failed" and "403" in run["error"]


def test_grok_research_parsing():
    notes = {
        "player_phrasing": [
            {"phrase": "save scum", "language": "en", "meaning": "reload", "example_post_ids": ["p1", "p99"]}
        ],
        "creative_hooks": [],
        "competitor_insights": [
            {"comparable": "XCOM", "complaints": ["RNG"], "unmet_wants": [], "example_post_ids": ["p1"]}
        ],
    }
    brief = {
        "summary": "S",
        "player_phrasing": notes["player_phrasing"],
        "creative_hooks": [],
        "competitor_insights": notes["competitor_insights"],
        "creators": [
            {"handle": "bob", "why": "big", "sample_post_id": "p1"},
            {"handle": "ghost", "why": "made up", "sample_post_id": "p1"},
        ],
    }
    replies = iter([notes, brief])

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        assert "tools" not in body
        return httpx.Response(
            200,
            json={
                "model": "grok-4.3",
                "usage": {"cost_in_usd_ticks": 10_000_000},
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(next(replies))}]}
                ],
            },
        )

    import asyncio

    p = GrokProvider("k", "https://api.x.ai/v1", "grok-4.3", transport=httpx.MockTransport(handler))
    g = Game(name="NK", comparable_games=["XCOM"])
    posts = [
        ResearchPostInput(
            ref="p1", comparable="XCOM", language="en", handle="bob", followers=9000, engagement=5, text="XCOM RNG"
        )
    ]
    n = asyncio.run(p.extract_research_notes(g, posts))
    assert n.player_phrasing[0].example_post_ids == ["p1"] or n.player_phrasing[0].phrase == "save scum"
    b = asyncio.run(p.synthesize_ua_brief(g, [n], [CreatorCandidate("bob", 9000, 1, ["XCOM"], "p1", "XCOM RNG")], {}))
    assert [c.handle for c in b.creators] == ["bob"] and b.creators[0].followers == 9000
    assert b.cost_usd == pytest.approx(0.001)  # synth call only; extract cost is on the notes
