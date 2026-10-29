"""Grok (xAI) provider using the Responses API (POST {base_url}/responses).

- generate_profile: brief + screenshots (base64 data URLs) -> structured JSON (text.format=json_schema).
- search_and_classify: still a stub (TODO: x_search tool on the Responses API).
"""

import base64
import json
import logging
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.models import Category, Game, GameProfile, Sentiment, SuggestedComparable, UABrief
from app.providers import grok_research as gr
from app.providers.base import CreatorCandidate, ImageInput, ProviderError, RawClassifiedPost, ResearchPostInput

log = logging.getLogger(__name__)

TICKS_PER_USD = 10_000_000_000
# xAI image understanding accepts jpg/jpeg and png only.
SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg"}
MAX_IMAGES = 8
LANGUAGE_NAMES = {"en": "English", "zh": "Simplified Chinese", "ja": "Japanese", "ko": "Korean"}

_PROFILE_SYSTEM = """You are a senior mobile/PC game user-acquisition (UA) strategist.
From the developer's brief (and any screenshots / key art), build a game profile used to research
comparable games on X and write UA creative. Be concrete and specific to THIS game; avoid generic filler.

Rules:
- themes: 4-8 short phrases capturing fantasy, core loop and emotional hooks players would care about.
- keywords_by_language: for EACH requested language, 8-15 search terms and short phrases the way real
  players naturally talk and post about games like this in that language (slang, genre shorthand,
  community terms, common hashtags without '#'). Write natively in each language; do NOT literally
  translate the English list. If the developer gives SEED KEYWORDS for a language, treat them as
  authoritative examples of real player phrasing: include them and match their register
  and style. Include the game's genre terms and the relevant comparable titles as players
  in that market actually refer to them.
- suggested_comparables: 3-6 real, released games with a strongly overlapping audience that are NOT in
  the developer's own comparable list (and not the game itself). One-sentence reason each.
- visual_style: 3-8 short descriptors (art direction, palette, camera, UI tone). Use the images if given;
  otherwise infer from the brief and say nothing about images.
- target_audience: 2-4 sentences: who they are, what they play, platforms/regions, what will convert them.
"""

_SCAN_PROMPT = """Search X for recent posts about the video game "{name}".
Keywords: {keywords}. Hashtags: {hashtags}. Handles: {handles}. Languages: {languages}.
Return ONLY a JSON array (max {max_posts} items) of objects with keys:
text, author, language (en|ja|ko|zh), sentiment (positive|neutral|negative),
category (bug|praise|question|influencer|other), url, posted_at (ISO 8601),
likes, reposts, replies, author_followers."""


class _Comparable(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=500)


class GrokProfilePayload(BaseModel):
    """Validates the model's structured output before mapping to the GameProfile dataclass."""

    themes: list[str]
    keywords_by_language: dict[str, list[str]]
    suggested_comparables: list[_Comparable]
    visual_style: list[str]
    target_audience: str


def profile_json_schema(languages: list[str]) -> dict:
    str_list = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {
            "themes": str_list,
            "keywords_by_language": {
                "type": "object",
                "properties": {lang: str_list for lang in languages},
                "required": list(languages),
                "additionalProperties": False,
            },
            "suggested_comparables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "reason": {"type": "string"}},
                    "required": ["name", "reason"],
                    "additionalProperties": False,
                },
            },
            "visual_style": str_list,
            "target_audience": {"type": "string"},
        },
        "required": ["themes", "keywords_by_language", "suggested_comparables", "visual_style", "target_audience"],
        "additionalProperties": False,
    }


def brief_text(game: Game, image_count: int, skipped_images: int, key_art_count: int = 0) -> str:
    langs = ", ".join(f"{code} ({LANGUAGE_NAMES.get(code, code)})" for code in game.languages)
    lines = [
        f"Game name: {game.name}",
        f"One-line pitch: {game.pitch or '-'}",
        f"Description: {game.description or '-'}",
        f"Genres: {', '.join(game.genres) or '-'}",
        f"Platforms: {', '.join(p.value for p in game.platforms) or '-'}",
        f"Target regions: {', '.join(game.regions) or '-'}",
        f"Languages for keywords: {langs}",
        f"What makes it different: {game.differentiators or '-'}",
        f"Developer's own comparable games (do NOT suggest these): {', '.join(game.comparable_games) or '-'}",
    ]
    if game.seed_keywords:
        lines.append("SEED KEYWORDS (authoritative player phrasing from the developer):")
        lines += [f"  {lang}: {', '.join(words)}" for lang, words in game.seed_keywords.items() if words]
    note = f"Attached images: {image_count}"
    if key_art_count:
        note += f" (the first {key_art_count} key art, the rest gameplay screenshots)"
    if skipped_images:
        note += f" ({skipped_images} unsupported image(s) omitted)"
    lines.append(note)
    return "\n".join(lines)


def _clean(xs: list[str], limit: int) -> list[str]:
    out: list[str] = []
    for x in xs:
        x = x.strip()
        if x and x.lower() not in {o.lower() for o in out}:
            out.append(x)
    return out[:limit]


class GrokProvider:
    name = "grok"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.x.ai/v1",
        model: str = "grok-4.3",
        timeout: float = 90.0,
        reasoning_effort: str | None = "low",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("XAI_API_KEY is required for GrokProvider")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.model = model
        self._timeout = timeout
        self._reasoning_effort = reasoning_effort
        self._transport = transport  # injectable for tests (httpx.MockTransport)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
        )

    async def _post_responses(self, payload: dict) -> dict:
        try:
            async with self._client() as client:
                resp = await client.post(f"{self._base_url}/responses", json=payload)
        except httpx.TimeoutException as e:
            raise ProviderError(f"xAI request timed out after {self._timeout:.0f}s") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"Could not reach xAI API: {type(e).__name__}") from e
        if resp.status_code >= 400:
            raise ProviderError(f"xAI API error {resp.status_code}: {_error_message(resp)}")
        try:
            return resp.json()
        except ValueError as e:
            raise ProviderError("xAI API returned non-JSON response") from e

    async def generate_profile(self, game: Game, images: list[ImageInput]) -> GameProfile:
        usable = [i for i in images if i.content_type in SUPPORTED_IMAGE_TYPES and i.path.is_file()][:MAX_IMAGES]
        skipped = len(images) - len(usable)
        key_art = sum(1 for i in usable if i.kind == "key_art")
        content: list[dict] = [{"type": "input_text", "text": brief_text(game, len(usable), skipped, key_art)}]
        for img in usable:
            b64 = base64.b64encode(img.path.read_bytes()).decode("ascii")
            content.append({"type": "input_image", "image_url": f"data:{img.content_type};base64,{b64}"})
        payload: dict = {
            "model": self.model,
            "instructions": _PROFILE_SYSTEM,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "game_profile",
                    "strict": True,
                    "schema": profile_json_schema(game.languages),
                }
            },
            "store": False,  # recommended by xAI when sending images
            "max_output_tokens": 4000,
        }
        if self._reasoning_effort:
            payload["reasoning"] = {"effort": self._reasoning_effort}

        data = await self._post_responses(payload)
        text = _output_text(data)
        try:
            parsed = GrokProfilePayload.model_validate_json(text)
        except ValidationError as e:
            raise ProviderError(f"xAI returned a profile that failed validation ({e.error_count()} errors)") from e

        ticks = (data.get("usage") or {}).get("cost_in_usd_ticks")
        cost = round(ticks / TICKS_PER_USD, 6) if isinstance(ticks, int | float) else None
        own = {c.lower() for c in game.comparable_games} | {game.name.lower()}
        return GameProfile(
            game_id=game.id,
            themes=_clean(parsed.themes, 12),
            keywords_by_language={
                lang: _clean(parsed.keywords_by_language.get(lang, []), 25) for lang in game.languages
            },
            suggested_comparables=[
                SuggestedComparable(name=c.name.strip(), reason=c.reason.strip())
                for c in parsed.suggested_comparables
                if c.name.strip().lower() not in own
            ][:8],
            visual_style=_clean(parsed.visual_style, 12),
            target_audience=parsed.target_audience.strip(),
            generated_by=self.name,
            model=str(data.get("model") or self.model),
            cost_usd=cost,
        )

    async def _structured(
        self, instructions: str, text: str, name: str, schema: dict, max_tokens: int
    ) -> tuple[dict, float, str]:
        """One strict-JSON Responses call without tools. Returns (parsed object, cost_usd, model)."""
        payload: dict = {
            "model": self.model,
            "instructions": instructions,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": text}]}],
            "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
            "store": False,
            "max_output_tokens": max_tokens,
        }
        if self._reasoning_effort:
            payload["reasoning"] = {"effort": self._reasoning_effort}
        data = await self._post_responses(payload)
        try:
            parsed = json.loads(_output_text(data))
        except json.JSONDecodeError as e:
            raise ProviderError(f"xAI returned invalid JSON for {name}") from e
        if not isinstance(parsed, dict):
            raise ProviderError(f"xAI returned a non-object for {name}")
        ticks = (data.get("usage") or {}).get("cost_in_usd_ticks")
        cost = round(ticks / TICKS_PER_USD, 6) if isinstance(ticks, int | float) else 0.0
        return parsed, cost, str(data.get("model") or self.model)

    async def extract_research_notes(self, game: Game, posts: list[ResearchPostInput]) -> UABrief:
        parsed, cost, model = await self._structured(
            gr.EXTRACT_SYSTEM, gr.batch_text(game, posts), "research_notes", gr.NOTES_SCHEMA, 6000
        )
        try:
            notes = gr.notes_from(parsed)
        except (TypeError, ValueError) as e:
            raise ProviderError("xAI research notes failed validation") from e
        notes.cost_usd, notes.model = cost, model
        return notes

    async def synthesize_ua_brief(
        self, game: Game, notes: list[UABrief], creators: list[CreatorCandidate], stats: dict
    ) -> UABrief:
        parsed, cost, model = await self._structured(
            gr.SYNTH_SYSTEM, gr.synth_text(game, notes, creators, stats), "ua_brief", gr.BRIEF_SCHEMA, 8000
        )
        try:
            brief = gr.brief_from(parsed, creators)
        except (TypeError, ValueError) as e:
            raise ProviderError("xAI UA brief failed validation") from e
        brief.cost_usd, brief.model = cost, model
        return brief

    async def search_and_classify(self, game: Game, max_posts: int) -> list[RawClassifiedPost]:
        """TODO: switch to Responses API + x_search tool. Not used by profile generation."""
        prompt = _SCAN_PROMPT.format(
            name=game.name,
            keywords=", ".join(game.keywords) or "-",
            hashtags=", ".join(f"#{h}" for h in game.hashtags) or "-",
            handles=", ".join(f"@{h}" for h in game.handles) or "-",
            languages=", ".join(game.languages),
            max_posts=max_posts,
        )
        data = await self._post_responses(
            {"model": self.model, "input": prompt, "tools": [{"type": "x_search"}], "store": False}
        )
        return [self._parse(item) for item in _extract_json(_output_text(data))][:max_posts]

    @staticmethod
    def _parse(d: dict) -> RawClassifiedPost:
        def enum(cls, v, default):
            try:
                return cls(str(v).lower())
            except ValueError:
                return default

        try:
            posted = datetime.fromisoformat(str(d.get("posted_at")).replace("Z", "+00:00"))
        except ValueError:
            posted = datetime.now(UTC)
        return RawClassifiedPost(
            text=str(d.get("text", "")),
            author=str(d.get("author", "unknown")),
            language=str(d.get("language", "en")),
            sentiment=enum(Sentiment, d.get("sentiment"), Sentiment.NEUTRAL),
            category=enum(Category, d.get("category"), Category.OTHER),
            url=str(d.get("url", "")),
            posted_at=posted,
            likes=int(d.get("likes") or 0),
            reposts=int(d.get("reposts") or 0),
            replies=int(d.get("replies") or 0),
            author_followers=int(d.get("author_followers") or 0),
        )


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.reason_phrase or "unknown error"
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)[:300]
    if isinstance(err, str):
        return err[:300]
    return str(body.get("detail") or body)[:300] if isinstance(body, dict) else resp.reason_phrase


def _output_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    for item in data.get("output") or []:
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    return part["text"]
    if data.get("status") == "incomplete":
        raise ProviderError(f"xAI response incomplete: {data.get('incomplete_details')}")
    raise ProviderError("xAI response contained no output text")


def _extract_json(content: str) -> list[dict]:
    start, end = content.find("["), content.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict)]
