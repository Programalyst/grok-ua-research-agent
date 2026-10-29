"""Research step domain models: X posts collected for comparable games and the resulting UA brief."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum

from app.models.domain import _id, _now


class ResearchStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class XAuthor:
    """An X account seen in research results (X user id is the primary key)."""

    id: str
    username: str
    name: str = ""
    followers: int = 0
    verified: bool = False
    description: str = ""
    updated_at: datetime = field(default_factory=_now)


@dataclass
class ResearchPost:
    run_id: str
    game_id: str
    x_id: str
    comparable: str  # comparable game this query targeted, or "keywords" for the keyword-set query
    language: str
    text: str
    author_id: str
    posted_at: datetime
    query: str = ""
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    quotes: int = 0
    id: str = field(default_factory=_id)

    @property
    def engagement(self) -> int:
        return self.likes + self.reposts * 2 + self.replies + self.quotes


@dataclass
class PlayerPhrase:
    phrase: str
    language: str
    meaning: str = ""
    example_post_ids: list[str] = field(default_factory=list)


@dataclass
class CreativeHook:
    title: str
    angle: str
    differentiator: str = ""
    evidence_post_ids: list[str] = field(default_factory=list)


@dataclass
class CompetitorInsight:
    comparable: str
    complaints: list[str] = field(default_factory=list)
    unmet_wants: list[str] = field(default_factory=list)
    example_post_ids: list[str] = field(default_factory=list)


@dataclass
class CreatorPick:
    handle: str
    followers: int
    why: str
    sample_post_id: str = ""
    sample_text: str = ""


@dataclass
class UABrief:
    summary: str = ""
    player_phrasing: list[PlayerPhrase] = field(default_factory=list)
    creative_hooks: list[CreativeHook] = field(default_factory=list)
    competitor_insights: list[CompetitorInsight] = field(default_factory=list)
    creators: list[CreatorPick] = field(default_factory=list)
    cost_usd: float = 0.0  # LLM cost of producing this brief (all batches)
    model: str = ""


@dataclass
class ResearchRun:
    game_id: str
    provider: str  # LLM provider name
    x_source: str  # "x_api" or "fake"
    max_posts_per_comparable: int
    max_posts_total: int
    status: ResearchStatus = ResearchStatus.RUNNING
    post_count: int = 0
    author_count: int = 0
    stats: dict = field(default_factory=dict)  # queries, per-comparable / per-language counts, filtered counts
    x_cost_usd: float = 0.0
    llm_cost_usd: float = 0.0
    brief: UABrief | None = None
    error: str | None = None
    id: str = field(default_factory=_id)
    started_at: datetime = field(default_factory=_now)
    finished_at: datetime | None = None

    @property
    def total_cost_usd(self) -> float:
        return round(self.x_cost_usd + self.llm_cost_usd, 6)


def brief_to_dict(b: UABrief) -> dict:
    return asdict(b)


def brief_from_dict(d: dict) -> UABrief:
    return UABrief(
        summary=d.get("summary", ""),
        player_phrasing=[PlayerPhrase(**x) for x in d.get("player_phrasing", [])],
        creative_hooks=[CreativeHook(**x) for x in d.get("creative_hooks", [])],
        competitor_insights=[CompetitorInsight(**x) for x in d.get("competitor_insights", [])],
        creators=[CreatorPick(**x) for x in d.get("creators", [])],
        cost_usd=float(d.get("cost_usd", 0.0)),
        model=d.get("model", ""),
    )
