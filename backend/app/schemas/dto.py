from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Language = Literal["en", "ja", "ko", "zh"]
PlatformName = Literal["pc", "console", "ios", "android", "web", "mac"]
SuggestionStatusName = Literal["suggested", "accepted", "rejected"]
ImageKindName = Literal["screenshot", "key_art"]
LONG_TEXT = 5000


def _clean(values: list[str], max_len: int = 100) -> list[str]:
    out: list[str] = []
    for v in values:
        v = v.strip()[:max_len]
        if v and v.lower() not in {o.lower() for o in out}:
            out.append(v)
    return out


class _BriefFields(BaseModel):
    @field_validator(
        "genres", "regions", "comparable_games", "keywords", "hashtags", "handles", mode="after", check_fields=False
    )
    @classmethod
    def _dedupe(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _clean(v)

    @field_validator("seed_keywords", mode="after", check_fields=False)
    @classmethod
    def _seed(cls, v: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
        """Per-language seed phrases, e.g. {"zh": ["战棋", "末日"]}. Normalized, deduped, empty langs dropped."""
        if v is None:
            return None
        if len(v) > 10:
            raise ValueError("seed_keywords supports at most 10 languages")
        out: dict[str, list[str]] = {}
        for lang, words in v.items():
            code = lang.strip().lower()[:10]
            cleaned = _clean(words, max_len=60)[:30]
            if code and cleaned:
                out[code] = cleaned
        return out


class GameCreate(_BriefFields):
    name: str = Field(min_length=1, max_length=200)
    pitch: str = Field(default="", max_length=280)
    description: str = Field(default="", max_length=LONG_TEXT)
    genres: list[str] = Field(default=[], max_length=15)
    platforms: list[PlatformName] = []
    regions: list[str] = Field(default=[], max_length=20)
    languages: list[Language] = ["en", "ja", "ko", "zh"]
    differentiators: str = Field(default="", max_length=LONG_TEXT)
    comparable_games: list[str] = Field(default=[], max_length=5)
    seed_keywords: dict[str, list[str]] = {}
    keywords: list[str] = []
    hashtags: list[str] = []
    handles: list[str] = []


class GameUpdate(_BriefFields):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    pitch: str | None = Field(default=None, max_length=280)
    description: str | None = Field(default=None, max_length=LONG_TEXT)
    genres: list[str] | None = Field(default=None, max_length=15)
    platforms: list[PlatformName] | None = None
    regions: list[str] | None = Field(default=None, max_length=20)
    languages: list[Language] | None = None
    differentiators: str | None = Field(default=None, max_length=LONG_TEXT)
    comparable_games: list[str] | None = Field(default=None, max_length=5)
    seed_keywords: dict[str, list[str]] | None = None
    keywords: list[str] | None = None
    hashtags: list[str] | None = None
    handles: list[str] | None = None


class ImageOut(BaseModel):
    id: str
    kind: ImageKindName
    width: int
    height: int
    filename: str
    content_type: str
    size_bytes: int
    url: str
    created_at: datetime


class GameOut(BaseModel):
    id: str
    name: str
    pitch: str
    description: str
    genres: list[str]
    platforms: list[str]
    regions: list[str]
    languages: list[str]
    differentiators: str
    comparable_games: list[str]
    seed_keywords: dict[str, list[str]]
    images: list[ImageOut]
    has_profile: bool
    keywords: list[str]
    hashtags: list[str]
    handles: list[str]
    created_at: datetime


class SuggestedComparableDTO(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=500)
    status: SuggestionStatusName = "suggested"


class GameProfileUpdate(BaseModel):
    themes: list[str] = Field(default=[], max_length=30)
    keywords_by_language: dict[Language, list[str]] = {}
    suggested_comparables: list[SuggestedComparableDTO] = Field(default=[], max_length=20)
    visual_style: list[str] = Field(default=[], max_length=30)
    target_audience: str = Field(default="", max_length=2000)


class GameProfileOut(BaseModel):
    game_id: str
    themes: list[str]
    keywords_by_language: dict[str, list[str]]
    suggested_comparables: list[SuggestedComparableDTO]
    visual_style: list[str]
    target_audience: str
    generated_by: str
    model: str
    cost_usd: float | None
    edited: bool
    updated_at: datetime


class ScanCreate(BaseModel):
    max_posts: int = Field(default=20, ge=1, le=200)


class ScanOut(BaseModel):
    id: str
    game_id: str
    provider: str
    status: str
    post_count: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class PostOut(BaseModel):
    id: str
    game_id: str
    scan_id: str
    text: str
    author: str
    author_followers: int
    language: str
    sentiment: str
    category: str
    url: str
    posted_at: datetime
    likes: int
    reposts: int
    replies: int
    engagement: int


class SentimentBucketOut(BaseModel):
    bucket_start: datetime
    positive: int
    neutral: int
    negative: int


class IssueCountOut(BaseModel):
    label: str
    count: int
    example_post_ids: list[str]


class SpikeOut(BaseModel):
    post_id: str
    author: str
    engagement: int
    reason: str


class InsightsOut(BaseModel):
    game_id: str
    total_posts: int
    sentiment_totals: dict[str, int]
    category_totals: dict[str, int]
    language_totals: dict[str, int]
    sentiment_over_time: list[SentimentBucketOut]
    top_issues: list[IssueCountOut]
    spikes: list[SpikeOut]
    generated_at: datetime


class HealthOut(BaseModel):
    status: str
    provider: str


# ---- research / UA brief -------------------------------------------------------------------------


class ResearchRunCreate(BaseModel):
    """Optional per-run caps; each is clamped to the server's configured maximum."""

    max_posts_per_comparable: int | None = Field(default=None, ge=10, le=100)
    max_posts_total: int | None = Field(default=None, ge=10, le=1000)
    max_searches: int | None = Field(default=None, ge=1, le=30)  # grok_x_search collector only


class ResearchEstimateOut(BaseModel):
    max_posts_per_comparable: int
    max_posts_total: int
    cost_per_post_usd: float
    max_x_cost_usd: float
    llm_reserve_usd: float
    max_total_cost_usd: float
    budget_limit_usd: float
    budget_spent_today_usd: float
    budget_remaining_usd: float
    can_run: bool
    x_source: str
    provider: str
    comparables: list[str]
    planned_queries: int
    collector: Literal["grok_x_search", "x_api"]
    max_searches: int | None
    cost_per_search_usd: float | None
    followers_verified: bool


FollowersSource = Literal["x_api", "grok_reported", "unknown"]


class PostRefOut(BaseModel):
    id: str
    url: str
    text: str
    author: str
    author_followers: int
    author_followers_source: FollowersSource
    language: str
    comparable: str
    engagement: int


class PlayerPhraseOut(BaseModel):
    phrase: str
    language: str
    meaning: str
    example_post_ids: list[str]


class CreativeHookOut(BaseModel):
    title: str
    angle: str
    differentiator: str
    evidence_post_ids: list[str]


class CompetitorInsightOut(BaseModel):
    comparable: str
    complaints: list[str]
    unmet_wants: list[str]
    example_post_ids: list[str]


class CreatorPickOut(BaseModel):
    handle: str
    profile_url: str
    followers: int
    followers_source: FollowersSource  # "grok_reported" = unverified count from Grok x_search, not the X API
    why: str
    sample_post_id: str
    sample_text: str


class UABriefOut(BaseModel):
    summary: str
    model: str
    player_phrasing: list[PlayerPhraseOut]
    creative_hooks: list[CreativeHookOut]
    competitor_insights: list[CompetitorInsightOut]
    creators: list[CreatorPickOut]


class ResearchRunSummaryOut(BaseModel):
    id: str
    game_id: str
    status: Literal["running", "completed", "failed"]
    provider: str
    x_source: str
    max_posts_per_comparable: int
    max_posts_total: int
    post_count: int
    author_count: int
    x_cost_usd: float
    llm_cost_usd: float
    total_cost_usd: float
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class ResearchRunOut(ResearchRunSummaryOut):
    stats: dict
    brief: UABriefOut | None
    posts: dict[str, PostRefOut]  # every post referenced by the brief, keyed by X post id
