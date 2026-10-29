from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.models import Category, Game, GameProfile, Sentiment, UABrief


@dataclass
class RawClassifiedPost:
    """Provider output: one X post already classified by the model."""

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


@dataclass
class ImageInput:
    path: Path
    content_type: str
    kind: str = "screenshot"  # screenshot | key_art


@dataclass
class ResearchPostInput:
    """A collected post as shown to the analysis model. `ref` is a short run-local id (p1, p2, ...)."""

    ref: str
    comparable: str
    language: str
    handle: str
    followers: int
    engagement: int
    text: str


@dataclass
class CreatorCandidate:
    """Pre-ranked author (ranked locally from real follower counts); the model only picks and explains."""

    handle: str
    followers: int
    post_count: int
    comparables: list[str]
    sample_ref: str
    sample_text: str


class ProviderError(Exception):
    """Upstream LLM failure (timeout, HTTP error, invalid output). Mapped to 502 at the API."""


class LLMProvider(Protocol):
    name: str

    async def search_and_classify(self, game: Game, max_posts: int) -> list[RawClassifiedPost]:
        """Search X for posts about the game and classify each one."""
        ...

    async def generate_profile(self, game: Game, images: list[ImageInput]) -> GameProfile:
        """Build a UA game profile from the user's brief (and optional screenshots/key art)."""
        ...

    async def extract_research_notes(self, game: Game, posts: list[ResearchPostInput]) -> UABrief:
        """Analyze ONE batch of collected posts (no web/X search). Returns partial brief (phrasing, hooks,
        competitor insights) whose post ids are the batch refs; cost_usd set if known."""
        ...

    async def synthesize_ua_brief(
        self, game: Game, notes: list[UABrief], creators: list[CreatorCandidate], stats: dict
    ) -> UABrief:
        """Merge batch notes into the final UA brief and pick creators from the candidates (by handle)."""
        ...
