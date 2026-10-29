"""X API v2 recent search (app-only bearer, read-only) plus an offline fake for tests/dev.

Docs: GET /2/tweets/search/recent (last 7 days), max_results 10..100, expansions=author_id.
"""

import hashlib
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx

from app.models import XAuthor

TWEET_FIELDS = "created_at,lang,public_metrics,author_id,entities"
USER_FIELDS = "username,name,public_metrics,verified,description"


class XApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def rate_limited(self) -> bool:
        return self.status_code == 429


@dataclass
class XPost:
    id: str
    text: str
    author_id: str
    lang: str
    created_at: datetime
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    quotes: int = 0
    url_count: int = 0


@dataclass
class XSearchPage:
    posts: list[XPost] = field(default_factory=list)
    users: dict[str, XAuthor] = field(default_factory=dict)
    next_token: str | None = None


class XClient(Protocol):
    source: str  # "x_api" | "fake"

    async def search_recent(self, query: str, max_results: int, next_token: str | None = None) -> XSearchPage: ...


def _parse_ts(v: str | None) -> datetime:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


def parse_search_response(body: dict) -> XSearchPage:
    users: dict[str, XAuthor] = {}
    for u in (body.get("includes") or {}).get("users") or []:
        pm = u.get("public_metrics") or {}
        users[str(u["id"])] = XAuthor(
            id=str(u["id"]),
            username=str(u.get("username", "")),
            name=str(u.get("name", "")),
            followers=int(pm.get("followers_count") or 0),
            verified=bool(u.get("verified")),
            description=str(u.get("description") or "")[:500],
        )
    out: list[XPost] = []
    for t in body.get("data") or []:
        pm = t.get("public_metrics") or {}
        out.append(
            XPost(
                id=str(t["id"]),
                text=str(t.get("text", "")),
                author_id=str(t.get("author_id", "")),
                lang=str(t.get("lang") or "und"),
                created_at=_parse_ts(t.get("created_at")),
                likes=int(pm.get("like_count") or 0),
                reposts=int(pm.get("retweet_count") or 0),
                replies=int(pm.get("reply_count") or 0),
                quotes=int(pm.get("quote_count") or 0),
                url_count=len((t.get("entities") or {}).get("urls") or []),
            )
        )
    return XSearchPage(posts=out, users=users, next_token=(body.get("meta") or {}).get("next_token"))


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.reason_phrase or "unknown error"
    if isinstance(body, dict):
        if body.get("detail") or body.get("title"):
            return str(body.get("detail") or body.get("title"))[:300]
        errs = body.get("errors")
        if isinstance(errs, list) and errs:
            return str(errs[0].get("message") or errs[0])[:300]
    return str(body)[:300]


class HttpXClient:
    source = "x_api"

    def __init__(
        self,
        bearer_token: str,
        base_url: str = "https://api.x.com/2",
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not bearer_token:
            raise ValueError("X_BEARER_TOKEN is required for HttpXClient")
        self._token = bearer_token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def search_recent(self, query: str, max_results: int, next_token: str | None = None) -> XSearchPage:
        params = {
            "query": query,
            "max_results": max(10, min(100, max_results)),
            "tweet.fields": TWEET_FIELDS,
            "expansions": "author_id",
            "user.fields": USER_FIELDS,
        }
        if next_token:
            params["next_token"] = next_token
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, headers={"Authorization": f"Bearer {self._token}"}
            ) as client:
                resp = await client.get(f"{self._base_url}/tweets/search/recent", params=params)
        except httpx.TimeoutException as e:
            raise XApiError(f"X API timed out after {self._timeout:.0f}s") from e
        except httpx.HTTPError as e:
            raise XApiError(f"Could not reach X API: {type(e).__name__}") from e
        if resp.status_code >= 400:
            raise XApiError(f"X API error {resp.status_code}: {_error_message(resp)}", resp.status_code)
        try:
            return parse_search_response(resp.json())
        except (ValueError, KeyError, TypeError) as e:
            raise XApiError("X API returned an unexpected response") from e


_FAKE_TEXT = {
    "en": [
        "{c} is still the best squad tactics game, permadeath makes every mission tense",
        "Wish {c} had a real base-building layer, the late game gets repetitive",
        "{c} RNG is brutal. 95% shot and I miss again lol",
        "Replaying {c} this week, the post-apocalyptic vibes are unmatched",
        "HUGE SALE: {c} 80% off this weekend only, grab the deal",
    ],
    "zh": ["{c} 战棋太上头了，末日题材永远的神", "{c} 后期内容太少了，希望有更多随机事件", "{c} 史低 折扣 快冲"],
    "ja": ["{c} の戦術バトル最高、終末世界の雰囲気が好き", "{c} の命中率ほんと信用できない", "{c} セール中！"],
    "ko": ["{c} 턴제 전략 너무 재밌다 아포칼립스 감성 최고", "{c} 후반부가 너무 지루해요", "{c} 할인 중"],
}


class FakeXClient:
    """Deterministic offline stand-in for X recent search. Returns a few posts per query incl. spam/duplicates."""

    source = "fake"

    def __init__(self, posts_per_query: int = 6, now: datetime | None = None) -> None:
        self.posts_per_query = posts_per_query
        self.calls: list[tuple[str, int]] = []
        self._now = now or datetime.now(UTC).replace(microsecond=0)

    async def search_recent(self, query: str, max_results: int, next_token: str | None = None) -> XSearchPage:
        self.calls.append((query, max_results))
        lang = next((tok[5:] for tok in query.split() if tok.startswith("lang:")), "en")
        subject = query.split('"')[1] if '"' in query else "this game"
        rng = random.Random(query)
        templates = _FAKE_TEXT.get(lang, _FAKE_TEXT["en"])
        page = XSearchPage()
        for i in range(min(self.posts_per_query, max_results)):
            uid = str(1000 + rng.randint(0, 40))
            followers = rng.choice([50, 300, 2_000, 15_000, 120_000])
            page.users[uid] = XAuthor(id=uid, username=f"player{uid}", name=f"Player {uid}", followers=followers)
            digest = hashlib.sha1(f"{query}:{i}".encode()).hexdigest()
            page.posts.append(
                XPost(
                    id=str(int(digest[:15], 16)),
                    text=templates[i % len(templates)].format(c=subject),
                    author_id=uid,
                    lang=lang,
                    created_at=self._now - timedelta(hours=i),
                    likes=rng.randint(0, 500),
                    reposts=rng.randint(0, 50),
                    replies=rng.randint(0, 30),
                )
            )
        return page
