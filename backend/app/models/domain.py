from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class Category(StrEnum):
    BUG = "bug"
    PRAISE = "praise"
    QUESTION = "question"
    INFLUENCER = "influencer"
    OTHER = "other"


class ScanStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Platform(StrEnum):
    PC = "pc"
    CONSOLE = "console"
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"
    MAC = "mac"


class SuggestionStatus(StrEnum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ImageKind(StrEnum):
    SCREENSHOT = "screenshot"
    KEY_ART = "key_art"


@dataclass
class GameImage:
    """An uploaded screenshot or key art. Files are stored normalized (PNG/JPEG, downscaled)."""

    game_id: str
    filename: str
    content_type: str
    size_bytes: int
    stored_name: str
    kind: ImageKind = ImageKind.SCREENSHOT
    width: int = 0
    height: int = 0
    id: str = field(default_factory=_id)
    created_at: datetime = field(default_factory=_now)


@dataclass
class UsageRecord:
    """One paid provider call, for cost tracking and the daily budget."""

    purpose: str
    provider: str
    model: str
    cost_usd: float
    game_id: str | None = None
    id: str = field(default_factory=_id)
    created_at: datetime = field(default_factory=_now)


@dataclass
class SuggestedComparable:
    name: str
    reason: str
    status: SuggestionStatus = SuggestionStatus.SUGGESTED


@dataclass
class GameProfile:
    game_id: str
    themes: list[str] = field(default_factory=list)
    keywords_by_language: dict[str, list[str]] = field(default_factory=dict)
    suggested_comparables: list[SuggestedComparable] = field(default_factory=list)
    visual_style: list[str] = field(default_factory=list)
    target_audience: str = ""
    generated_by: str = ""
    model: str = ""
    cost_usd: float | None = None
    edited: bool = False
    updated_at: datetime = field(default_factory=_now)


@dataclass
class Game:
    name: str
    pitch: str = ""
    description: str = ""
    genres: list[str] = field(default_factory=list)
    platforms: list[Platform] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    differentiators: str = ""
    comparable_games: list[str] = field(default_factory=list)
    seed_keywords: dict[str, list[str]] = field(default_factory=dict)
    images: list[GameImage] = field(default_factory=list)
    profile: GameProfile | None = None
    keywords: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["en", "ja", "ko", "zh"])
    handles: list[str] = field(default_factory=list)
    id: str = field(default_factory=_id)
    created_at: datetime = field(default_factory=_now)

    def images_of(self, kind: ImageKind) -> list[GameImage]:
        return [i for i in self.images if i.kind == kind]


@dataclass
class Post:
    game_id: str
    scan_id: str
    text: str
    author: str
    language: str
    sentiment: Sentiment
    category: Category
    url: str
    posted_at: datetime
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    author_followers: int = 0
    id: str = field(default_factory=_id)

    @property
    def engagement(self) -> int:
        return self.likes + self.reposts + self.replies


@dataclass
class Scan:
    game_id: str
    provider: str
    status: ScanStatus = ScanStatus.PENDING
    post_count: int = 0
    error: str | None = None
    id: str = field(default_factory=_id)
    started_at: datetime = field(default_factory=_now)
    finished_at: datetime | None = None


@dataclass
class SentimentBucket:
    bucket_start: datetime
    positive: int = 0
    neutral: int = 0
    negative: int = 0


@dataclass
class IssueCount:
    label: str
    count: int
    example_post_ids: list[str] = field(default_factory=list)


@dataclass
class Spike:
    post_id: str
    author: str
    engagement: int
    reason: str


@dataclass
class Insights:
    game_id: str
    total_posts: int
    sentiment_totals: dict[str, int]
    category_totals: dict[str, int]
    language_totals: dict[str, int]
    sentiment_over_time: list[SentimentBucket]
    top_issues: list[IssueCount]
    spikes: list[Spike]
    generated_at: datetime = field(default_factory=_now)
