"""Post collectors for the research step.

* ``XApiCollector``      – X API v2 recent search (bearer token; billed per post read).
* ``GrokXSearchCollector`` – grok-4.3 with xAI's server-side ``x_search`` tool (billed to the xAI balance).
* ``FakeGrokXSearchCollector`` – deterministic offline stand-in for tests/dev.

Grok output is untrusted: every post must carry a real ``x.com/<handle>/status/<id>`` URL whose id is a
plausible snowflake inside the search window, and (when xAI returns citations) must be one of the posts the
tool actually fetched. Follower counts from Grok are *reported*, not verified.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx

from app.models import XAuthor
from app.x.client import XApiError, XClient, XPost, XSearchPage

TICKS_PER_USD = 10_000_000_000
TWITTER_EPOCH_MS = 1288834974657
STATUS_URL = re.compile(
    r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15}|i(?:/web)?)/status/(\d{15,20})(?:[/?#]|$)"
)
LANGS = {"en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean"}


@dataclass
class CollectTask:
    bucket: str  # comparable name or "keywords"
    lang: str  # primary language ("en", "ja", ...) or "multi"
    query: str  # X query string (x_api) or human-readable search description (grok)
    max_posts: int
    terms: list[str] = field(default_factory=list)


@dataclass
class CollectResult:
    page: XSearchPage
    cost_usd: float
    model: str
    detail: dict = field(default_factory=dict)  # collector-specific stats (search calls, drops, cost split)


class Collector(Protocol):
    source: str  # "x_api" | "grok_x_search" | "fake" | "fake_grok"
    followers_verified: bool
    kind: str  # "x_api" | "grok_x_search" — decides query planning and cost estimate

    async def collect(self, task: CollectTask) -> CollectResult: ...


class XApiCollector:
    kind = "x_api"
    followers_verified = True

    def __init__(self, client: XClient, cost_per_post_usd: float = 0.005) -> None:
        self.client, self.cost_per_post_usd = client, cost_per_post_usd
        self.source = client.source

    async def collect(self, task: CollectTask) -> CollectResult:
        page = await self.client.search_recent(task.query, task.max_posts)
        page.posts = page.posts[: task.max_posts]
        return CollectResult(page, round(len(page.posts) * self.cost_per_post_usd, 6), "recent_search")


# ---- Grok x_search ---------------------------------------------------------------------------------------

POSTS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["posts"],
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["url", "handle", "text", "lang", "date", "followers"],
                "properties": {
                    "url": {"type": "string"},
                    "handle": {"type": "string"},
                    "text": {"type": "string"},
                    "lang": {"type": "string"},
                    "date": {"type": "string"},
                    "followers": {"type": ["integer", "null"]},
                },
            },
        }
    },
}

SEARCH_INSTRUCTIONS = """You collect raw X posts for game-marketing research. Use the x_search tool.
Return ONLY posts you actually saw in x_search results, copied verbatim - never invent, paraphrase or
merge posts. Each url must be the exact https://x.com/<handle>/status/<id> of that post.
Wanted: players and creators sharing opinions, experiences, complaints, wishes, comparisons, memes, clips.
Not wanted: sale/discount/deal/bundle/giveaway posts, store or price-tracker bots, official studio or
publisher announcements, news headlines without opinion, reposts, link-only posts.
lang is the post's ISO 639-1 code. date is ISO 8601. followers is the author's follower count only if it
appeared in the search results, else null. Fewer real posts beat more doubtful ones."""


def snowflake_time(post_id: str) -> datetime | None:
    try:
        ms = (int(post_id) >> 22) + TWITTER_EPOCH_MS
        return datetime.fromtimestamp(ms / 1000, UTC)
    except (ValueError, OverflowError, OSError):
        return None


def search_prompt(task: CollectTask, days: int) -> str:
    if task.lang == "cjk":
        lang_line = "Only posts written in Japanese, Chinese or Korean."
    elif task.lang in LANGS and task.lang != "en":
        lang_line = f"Only posts written in {LANGS[task.lang]} ({task.lang})."
    else:
        lang_line = "Mostly English posts; include Japanese, Chinese or Korean posts too if you find them."
    terms = f" Useful search terms: {', '.join(task.terms)}." if task.terms else ""
    return (
        f"Find up to {task.max_posts} recent X posts by players discussing {task.query}.{terms} {lang_line} "
        "Prefer posts with substance (why they love or hate it, what they wish it had) and some engagement."
    )


def parse_grok_posts(
    items: list, cited_ids: set[str], window_start: datetime, now: datetime, max_posts: int
) -> tuple[XSearchPage, dict[str, int]]:
    """Validate Grok-reported posts. Returns the page plus drop counts by reason."""
    drops = {"bad_url": 0, "bad_id_time": 0, "not_cited": 0, "duplicate": 0, "empty": 0}
    page = XSearchPage()
    seen: set[str] = set()
    for it in items:
        if not isinstance(it, dict):
            drops["empty"] += 1
            continue
        m = STATUS_URL.match(str(it.get("url", "")).strip())
        text = str(it.get("text") or "").strip()
        if not text:
            drops["empty"] += 1
            continue
        if not m:
            drops["bad_url"] += 1
            continue
        url_handle, pid = m.group(1), m.group(2)
        ts = snowflake_time(pid)
        if ts is None or ts < window_start - timedelta(days=1) or ts > now + timedelta(hours=1):
            drops["bad_id_time"] += 1
            continue
        if cited_ids and pid not in cited_ids:
            drops["not_cited"] += 1
            continue
        if pid in seen:
            drops["duplicate"] += 1
            continue
        seen.add(pid)
        handle = "" if url_handle in ("i", "i/web") else url_handle
        handle = handle or str(it.get("handle") or "").lstrip("@").strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
            drops["bad_url"] += 1
            continue
        followers = it.get("followers")
        author_id = f"h:{handle.lower()}"
        page.users.setdefault(
            author_id,
            XAuthor(
                id=author_id,
                username=handle,
                followers=int(followers) if isinstance(followers, int) and followers > 0 else 0,
            ),
        )
        page.posts.append(
            XPost(
                id=pid,
                text=text[:2000],
                author_id=author_id,
                lang=str(it.get("lang") or "und")[:5].lower(),
                created_at=ts,  # from the snowflake id, not the model
            )
        )
        if len(page.posts) >= max_posts:
            break
    return page, drops


def cited_status_ids(data: dict) -> set[str]:
    ids: set[str] = set()
    urls = list(data.get("citations") or [])
    for item in data.get("output") or []:
        for c in item.get("content") or [] if isinstance(item, dict) else []:
            urls += [a.get("url", "") for a in c.get("annotations") or [] if isinstance(a, dict)]
    for u in urls:
        if isinstance(u, dict):
            u = u.get("url", "")
        if m := re.search(r"/status/(\d{15,20})", str(u)):
            ids.add(m.group(1))
    return ids


def cost_split(usage: dict, cost_per_post_usd: float) -> dict:
    ticks = usage.get("cost_in_usd_ticks")
    total = round(ticks / TICKS_PER_USD, 6) if isinstance(ticks, int | float) else 0.0
    tools = usage.get("server_side_tool_usage_details") or {}
    fetched = int(tools.get("x_posts_fetched") or 0)
    search = round(min(total, fetched * cost_per_post_usd), 6)
    return {
        "cost_usd": total,
        "search_usd_est": search,
        "tokens_usd_est": round(total - search, 6),
        "x_search_calls": int(tools.get("x_search_calls") or 0),
        "x_posts_fetched": fetched,
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
    }


def _output_text(data: dict) -> str:
    for item in data.get("output") or []:
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") == "output_text":
                    return c.get("text", "")
    return ""


class GrokXSearchCollector:
    kind = "grok_x_search"
    source = "grok_x_search"
    followers_verified = False

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.x.ai/v1",
        model: str = "grok-4.3",
        *,
        days: int = 90,
        max_tool_calls: int = 3,
        excluded_handles: list[str] | None = None,
        cost_per_post_usd: float = 0.005,
        timeout: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._key, self._base, self.model = api_key, base_url.rstrip("/"), model
        self.days, self.max_tool_calls = days, max_tool_calls
        self.excluded = [h.lstrip("@") for h in (excluded_handles or [])][:20]
        self.cost_per_post_usd, self._timeout, self._transport = cost_per_post_usd, timeout, transport

    def payload(self, task: CollectTask, now: datetime) -> dict:
        tool: dict = {
            "type": "x_search",
            "from_date": (now - timedelta(days=self.days)).date().isoformat(),
            "to_date": (now + timedelta(days=1)).date().isoformat(),
        }
        if self.excluded:
            tool["excluded_x_handles"] = self.excluded
        return {
            "model": self.model,
            "instructions": SEARCH_INSTRUCTIONS,
            "input": [{"role": "user", "content": search_prompt(task, self.days)}],
            "tools": [tool],
            "max_tool_calls": self.max_tool_calls,
            "text": {"format": {"type": "json_schema", "name": "x_posts", "strict": True, "schema": POSTS_SCHEMA}},
            "store": False,
        }

    async def collect(self, task: CollectTask) -> CollectResult:
        now = datetime.now(UTC)
        headers = {"Authorization": f"Bearer {self._key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport, headers=headers) as c:
                resp = await c.post(f"{self._base}/responses", json=self.payload(task, now))
        except httpx.HTTPError as e:
            raise XApiError(f"xAI x_search request failed: {type(e).__name__}") from e
        if resp.status_code != 200:
            raise XApiError(f"xAI x_search error {resp.status_code}: {resp.text[:200]}", status_code=resp.status_code)
        data = resp.json()
        split = cost_split(data.get("usage") or {}, self.cost_per_post_usd)
        try:
            import json

            items = json.loads(_output_text(data) or "{}").get("posts") or []
        except (ValueError, AttributeError):
            items = []
        cited = cited_status_ids(data)
        page, drops = parse_grok_posts(items, cited, now - timedelta(days=self.days), now, task.max_posts)
        detail = {**split, "reported": len(items), "cited": len(cited), "dropped": drops}
        return CollectResult(page, split["cost_usd"], str(data.get("model") or self.model), detail)


class FakeGrokXSearchCollector:
    """Deterministic: per task returns valid posts plus one bad-URL, one uncited and one spam post."""

    kind = "grok_x_search"
    source = "fake_grok"
    followers_verified = False

    def __init__(self, posts_per_task: int = 6, cost_per_task_usd: float = 0.05) -> None:
        self.posts_per_task, self.cost_per_task_usd = posts_per_task, cost_per_task_usd
        self.calls: list[CollectTask] = []

    async def collect(self, task: CollectTask) -> CollectResult:
        self.calls.append(task)
        now = datetime.now(UTC)
        base = int(hashlib.sha1(f"{task.bucket}|{task.lang}".encode()).hexdigest()[:6], 16)
        lang = task.lang if task.lang in LANGS else "en"
        items, cited = [], set()
        for i in range(self.posts_per_task):
            ms = int((now - timedelta(days=1 + i)).timestamp() * 1000) - TWITTER_EPOCH_MS
            pid = str((ms << 22) + base + i)
            cited.add(pid)
            items.append(
                {
                    "url": f"https://x.com/player{(base + i) % 9}/status/{pid}",
                    "handle": f"player{(base + i) % 9}",
                    "text": f"{task.bucket}: wish the late game had more variety, combat still great #{i}",
                    "lang": lang,
                    "date": now.isoformat(),
                    "followers": [None, 1200, 45000][i % 3],
                }
            )
        items.append(
            {
                "url": "https://example.com/nope",
                "handle": "x",
                "text": "made up",
                "lang": "en",
                "date": "",
                "followers": None,
            }
        )
        items.append(
            {
                "url": f"https://x.com/ghost/status/{int(max(cited)) + 7}",
                "handle": "ghost",
                "text": "uncited post",
                "lang": "en",
                "date": "",
                "followers": None,
            }
        )
        spam_id = str(int(min(cited)) - 1)
        cited.add(spam_id)
        items.append(
            {
                "url": f"https://x.com/dealbot/status/{spam_id}",
                "handle": "dealbot",
                "text": f"{task.bucket} 80% off today! https://t.co/x",
                "lang": "en",
                "date": "",
                "followers": 10,
            }
        )
        page, drops = parse_grok_posts(items, cited, now - timedelta(days=90), now, task.max_posts)
        detail = {
            "cost_usd": self.cost_per_task_usd,
            "search_usd_est": self.cost_per_task_usd * 0.8,
            "tokens_usd_est": self.cost_per_task_usd * 0.2,
            "x_search_calls": 1,
            "x_posts_fetched": len(items),
            "reported": len(items),
            "cited": len(cited),
            "dropped": drops,
        }
        return CollectResult(page, self.cost_per_task_usd, "fake-grok", detail)
