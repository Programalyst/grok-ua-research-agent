import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.api.deps import get_collector
from app.main import app
from app.models import Game
from app.services.research_service import ResearchLimits, plan_grok_tasks
from app.x import CollectTask, FakeGrokXSearchCollector, GrokXSearchCollector
from app.x.collectors import TWITTER_EPOCH_MS, cited_status_ids, cost_split, parse_grok_posts, snowflake_time
from tests.test_research import nk  # noqa: F401  (fixture)


def sid(days_ago: float, salt: int = 0) -> str:
    ms = int((datetime.now(UTC) - timedelta(days=days_ago)).timestamp() * 1000) - TWITTER_EPOCH_MS
    return str((ms << 22) + salt)


def test_snowflake_roundtrip():
    t = snowflake_time(sid(3))
    assert t and abs((datetime.now(UTC) - t) - timedelta(days=3)) < timedelta(seconds=5)


def test_parse_validation():
    now = datetime.now(UTC)
    good, old, uncited = sid(2, 1), sid(400, 2), sid(1, 3)
    items = [
        {
            "url": f"https://x.com/alice/status/{good}",
            "handle": "wrong",
            "text": "love it",
            "lang": "en",
            "date": "",
            "followers": 5000,
        },
        {
            "url": f"https://x.com/alice/status/{good}",
            "handle": "alice",
            "text": "dupe",
            "lang": "en",
            "date": "",
            "followers": None,
        },
        {"url": "https://x.com/bob", "handle": "bob", "text": "no status", "lang": "en", "date": "", "followers": None},
        {
            "url": f"https://x.com/old/status/{old}",
            "handle": "old",
            "text": "old",
            "lang": "en",
            "date": "",
            "followers": None,
        },
        {
            "url": "https://x.com/fake/status/123456789012345678901",
            "handle": "f",
            "text": "x",
            "lang": "en",
            "date": "",
            "followers": None,
        },
        {
            "url": f"https://x.com/carol/status/{uncited}",
            "handle": "carol",
            "text": "hm",
            "lang": "ja",
            "date": "",
            "followers": None,
        },
    ]
    page, drops = parse_grok_posts(items, {good, old}, now - timedelta(days=90), now, 50)
    assert [p.id for p in page.posts] == [good]
    assert page.users["h:alice"].username == "alice" and page.users["h:alice"].followers == 5000
    assert drops["duplicate"] == 1 and drops["bad_url"] == 2 and drops["bad_id_time"] == 1 and drops["not_cited"] == 1
    # without citations we keep posts that pass the URL/time checks
    page2, _ = parse_grok_posts(items, set(), now - timedelta(days=90), now, 50)
    assert {p.id for p in page2.posts} == {good, uncited}


def test_citations_and_cost_split():
    data = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "{}",
                        "annotations": [{"type": "url_citation", "url": "https://x.com/i/status/2109657395479945346"}],
                    }
                ],
            }
        ],
        "citations": ["https://x.com/a/status/2109657395479945347"],
    }
    assert cited_status_ids(data) == {"2109657395479945346", "2109657395479945347"}
    split = cost_split(
        {
            "cost_in_usd_ticks": 2_240_772_000,
            "server_side_tool_usage_details": {"x_search_calls": 4, "x_posts_fetched": 38},
        },
        0.005,
    )
    assert split["cost_usd"] == pytest.approx(0.224077)
    assert split["search_usd_est"] == pytest.approx(0.19) and split["tokens_usd_est"] == pytest.approx(0.034077)


def test_plan_grok_tasks():
    g = Game(name="NK", comparable_games=["A", "B", "C", "D", "E"], languages=["en", "zh", "ja", "ko"])
    lim = ResearchLimits(25, 200, 0.005, collector_kind="grok_x_search", max_searches=5)
    tasks = plan_grok_tasks(g, lim)
    assert [t.bucket for t in tasks] == ["A", "B", "C", "D", "keywords"] and tasks[-1].lang == "cjk"
    lim.max_searches = 9
    tasks = plan_grok_tasks(g, lim)
    assert [t.lang for t in tasks][-3:] == ["zh", "ja", "ko"]


def test_http_collector_payload_and_parse():
    good = sid(5, 9)
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        body = {
            "posts": [
                {
                    "url": f"https://x.com/dana/status/{good}",
                    "handle": "dana",
                    "text": "XCOM RNG hurts",
                    "lang": "en",
                    "date": "",
                    "followers": 900,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "model": "grok-4.3",
                "usage": {
                    "cost_in_usd_ticks": 1_000_000_000,
                    "server_side_tool_usage_details": {"x_posts_fetched": 10},
                },
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(body),
                                "annotations": [{"type": "url_citation", "url": f"https://x.com/i/status/{good}"}],
                            }
                        ],
                    }
                ],
            },
        )

    c = GrokXSearchCollector("k", excluded_handles=["@SteamDB"], transport=httpx.MockTransport(handler))
    res = asyncio.run(c.collect(CollectTask("XCOM", "multi", 'the game "XCOM"', 20)))
    tool = seen["tools"][0]
    assert tool["type"] == "x_search" and tool["excluded_x_handles"] == ["SteamDB"]
    assert tool["from_date"] < tool["to_date"] and seen["max_tool_calls"] == 3
    assert seen["text"]["format"]["type"] == "json_schema"
    assert [p.id for p in res.page.posts] == [good] and res.cost_usd == pytest.approx(0.1)
    assert res.detail["search_usd_est"] == pytest.approx(0.05)


def test_endpoint_with_fake_grok(client, nk):  # noqa: F811
    fake = FakeGrokXSearchCollector()
    app.dependency_overrides[get_collector] = lambda: fake
    est = client.get(f"/api/v1/games/{nk['id']}/research/estimate", params={"max_searches": 3}).json()
    assert est["collector"] == "grok_x_search" and est["max_searches"] == 3
    assert est["max_total_cost_usd"] == pytest.approx(3 * 0.25 + 0.10) and not est["followers_verified"]
    r = client.post(f"/api/v1/games/{nk['id']}/research", json={"max_searches": 3, "max_posts_total": 50})
    run = r.json()
    assert r.status_code == 201 and run["status"] == "completed", run
    assert len(fake.calls) == 3 and run["x_cost_usd"] == pytest.approx(0.15)
    assert run["stats"]["followers_source"] == "grok_reported"
    assert run["stats"]["collector_cost"]["dropped"]["bad_url"] == 3
    assert run["stats"]["filtered"]["spam"] >= 3
    for c in run["brief"]["creators"]:
        assert c["followers_source"] in ("grok_reported", "unknown")
    for p in run["posts"].values():
        assert p["url"].startswith("https://x.com/") and "/status/" in p["url"]
