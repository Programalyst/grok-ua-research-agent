"""Explicit mapping between domain dataclasses and API DTOs."""

from dataclasses import asdict
from datetime import UTC, datetime

from app.models import (
    Game,
    GameImage,
    GameProfile,
    Insights,
    Platform,
    Post,
    ResearchPost,
    ResearchRun,
    Scan,
    SuggestedComparable,
    SuggestionStatus,
    UABrief,
    XAuthor,
)
from app.schemas.dto import (
    CompetitorInsightOut,
    CreativeHookOut,
    CreatorPickOut,
    GameCreate,
    GameOut,
    GameProfileOut,
    GameProfileUpdate,
    GameUpdate,
    ImageOut,
    InsightsOut,
    IssueCountOut,
    PlayerPhraseOut,
    PostOut,
    PostRefOut,
    ResearchRunOut,
    ResearchRunSummaryOut,
    ScanOut,
    SentimentBucketOut,
    SpikeOut,
    SuggestedComparableDTO,
    UABriefOut,
)

API_PREFIX = "/api/v1"


def game_from_create(dto: GameCreate) -> Game:
    return Game(
        name=dto.name.strip(),
        pitch=dto.pitch.strip(),
        description=dto.description.strip(),
        genres=list(dto.genres),
        platforms=[Platform(p) for p in dto.platforms],
        regions=list(dto.regions),
        languages=list(dto.languages),
        differentiators=dto.differentiators.strip(),
        comparable_games=list(dto.comparable_games),
        seed_keywords=dict(dto.seed_keywords),
        keywords=list(dto.keywords),
        hashtags=[h.lstrip("#") for h in dto.hashtags],
        handles=[h.lstrip("@") for h in dto.handles],
    )


def apply_game_update(game: Game, dto: GameUpdate) -> Game:
    if dto.name is not None:
        game.name = dto.name.strip()
    if dto.pitch is not None:
        game.pitch = dto.pitch.strip()
    if dto.description is not None:
        game.description = dto.description.strip()
    if dto.genres is not None:
        game.genres = list(dto.genres)
    if dto.platforms is not None:
        game.platforms = [Platform(p) for p in dto.platforms]
    if dto.regions is not None:
        game.regions = list(dto.regions)
    if dto.languages is not None:
        game.languages = list(dto.languages)
    if dto.differentiators is not None:
        game.differentiators = dto.differentiators.strip()
    if dto.comparable_games is not None:
        game.comparable_games = list(dto.comparable_games)
    if dto.seed_keywords is not None:
        game.seed_keywords = dict(dto.seed_keywords)
    if dto.keywords is not None:
        game.keywords = list(dto.keywords)
    if dto.hashtags is not None:
        game.hashtags = [h.lstrip("#") for h in dto.hashtags]
    if dto.handles is not None:
        game.handles = [h.lstrip("@") for h in dto.handles]
    return game


def image_url(s: GameImage) -> str:
    return f"{API_PREFIX}/games/{s.game_id}/images/{s.id}"


def image_to_out(s: GameImage) -> ImageOut:
    return ImageOut(
        id=s.id,
        kind=s.kind.value,
        width=s.width,
        height=s.height,
        filename=s.filename,
        content_type=s.content_type,
        size_bytes=s.size_bytes,
        url=image_url(s),
        created_at=s.created_at,
    )


def game_to_out(g: Game) -> GameOut:
    return GameOut(
        id=g.id,
        name=g.name,
        pitch=g.pitch,
        description=g.description,
        genres=g.genres,
        platforms=[p.value for p in g.platforms],
        regions=g.regions,
        languages=g.languages,
        differentiators=g.differentiators,
        comparable_games=g.comparable_games,
        seed_keywords=g.seed_keywords,
        images=[image_to_out(i) for i in g.images],
        has_profile=g.profile is not None,
        keywords=g.keywords,
        hashtags=g.hashtags,
        handles=g.handles,
        created_at=g.created_at,
    )


def profile_to_out(p: GameProfile) -> GameProfileOut:
    return GameProfileOut(
        game_id=p.game_id,
        themes=p.themes,
        keywords_by_language={k: list(v) for k, v in p.keywords_by_language.items()},
        suggested_comparables=[
            SuggestedComparableDTO(name=c.name, reason=c.reason, status=c.status.value) for c in p.suggested_comparables
        ],
        visual_style=p.visual_style,
        target_audience=p.target_audience,
        generated_by=p.generated_by,
        model=p.model,
        cost_usd=p.cost_usd,
        edited=p.edited,
        updated_at=p.updated_at,
    )


def profile_from_update(game_id: str, dto: GameProfileUpdate, previous: GameProfile | None) -> GameProfile:
    clean = lambda xs: [x.strip() for x in xs if x.strip()]  # noqa: E731
    return GameProfile(
        game_id=game_id,
        themes=clean(dto.themes),
        keywords_by_language={lang: clean(kws) for lang, kws in dto.keywords_by_language.items()},
        suggested_comparables=[
            SuggestedComparable(name=c.name.strip(), reason=c.reason.strip(), status=SuggestionStatus(c.status))
            for c in dto.suggested_comparables
        ],
        visual_style=clean(dto.visual_style),
        target_audience=dto.target_audience.strip(),
        generated_by=previous.generated_by if previous else "manual",
        model=previous.model if previous else "",
        cost_usd=previous.cost_usd if previous else None,
        edited=True,
        updated_at=datetime.now(UTC),
    )


def scan_to_out(s: Scan) -> ScanOut:
    return ScanOut(
        id=s.id,
        game_id=s.game_id,
        provider=s.provider,
        status=s.status.value,
        post_count=s.post_count,
        error=s.error,
        started_at=s.started_at,
        finished_at=s.finished_at,
    )


def post_to_out(p: Post) -> PostOut:
    return PostOut(
        id=p.id,
        game_id=p.game_id,
        scan_id=p.scan_id,
        text=p.text,
        author=p.author,
        author_followers=p.author_followers,
        language=p.language,
        sentiment=p.sentiment.value,
        category=p.category.value,
        url=p.url,
        posted_at=p.posted_at,
        likes=p.likes,
        reposts=p.reposts,
        replies=p.replies,
        engagement=p.engagement,
    )


def insights_to_out(i: Insights) -> InsightsOut:
    return InsightsOut(
        game_id=i.game_id,
        total_posts=i.total_posts,
        sentiment_totals=i.sentiment_totals,
        category_totals=i.category_totals,
        language_totals=i.language_totals,
        sentiment_over_time=[
            SentimentBucketOut(bucket_start=b.bucket_start, positive=b.positive, neutral=b.neutral, negative=b.negative)
            for b in i.sentiment_over_time
        ],
        top_issues=[
            IssueCountOut(label=t.label, count=t.count, example_post_ids=t.example_post_ids) for t in i.top_issues
        ],
        spikes=[
            SpikeOut(post_id=s.post_id, author=s.author, engagement=s.engagement, reason=s.reason) for s in i.spikes
        ],
        generated_at=i.generated_at,
    )


# ---- research ------------------------------------------------------------------------------------


def post_url(x_id: str, username: str = "") -> str:
    return f"https://x.com/{username or 'i/web'}/status/{x_id}"


def research_summary_to_out(r: ResearchRun) -> ResearchRunSummaryOut:
    return ResearchRunSummaryOut(
        id=r.id,
        game_id=r.game_id,
        status=r.status.value,
        provider=r.provider,
        x_source=r.x_source,
        max_posts_per_comparable=r.max_posts_per_comparable,
        max_posts_total=r.max_posts_total,
        post_count=r.post_count,
        author_count=r.author_count,
        x_cost_usd=r.x_cost_usd,
        llm_cost_usd=r.llm_cost_usd,
        total_cost_usd=r.total_cost_usd,
        error=r.error,
        started_at=r.started_at,
        finished_at=r.finished_at,
    )


def followers_source(stats: dict, followers: int) -> str:
    if stats.get("followers_source", "x_api") == "x_api":
        return "x_api"
    return "grok_reported" if followers > 0 else "unknown"


def brief_to_out(b: UABrief, stats: dict | None = None) -> UABriefOut:
    stats = stats or {}
    return UABriefOut(
        summary=b.summary,
        model=b.model,
        player_phrasing=[PlayerPhraseOut(**asdict(x)) for x in b.player_phrasing],
        creative_hooks=[CreativeHookOut(**asdict(x)) for x in b.creative_hooks],
        competitor_insights=[CompetitorInsightOut(**asdict(x)) for x in b.competitor_insights],
        creators=[
            CreatorPickOut(
                **asdict(x),
                profile_url=f"https://x.com/{x.handle}",
                followers_source=followers_source(stats, x.followers),
            )
            for x in b.creators
        ],
    )


def research_to_out(r: ResearchRun, posts: list[ResearchPost], authors: dict[str, XAuthor]) -> ResearchRunOut:
    refs: set[str] = set()
    if r.brief:
        for ph in r.brief.player_phrasing:
            refs.update(ph.example_post_ids)
        for h in r.brief.creative_hooks:
            refs.update(h.evidence_post_ids)
        for c in r.brief.competitor_insights:
            refs.update(c.example_post_ids)
        refs.update(c.sample_post_id for c in r.brief.creators if c.sample_post_id)
    index: dict[str, PostRefOut] = {}
    for p in posts:
        if p.x_id in refs:
            a = authors.get(p.author_id)
            index[p.x_id] = PostRefOut(
                id=p.x_id,
                url=post_url(p.x_id, a.username if a else ""),
                text=p.text,
                author=a.username if a else "",
                author_followers=a.followers if a else 0,
                author_followers_source=followers_source(r.stats, a.followers if a else 0),
                language=p.language,
                comparable=p.comparable,
                engagement=p.engagement,
            )
    return ResearchRunOut(
        **research_summary_to_out(r).model_dump(),
        stats=r.stats,
        brief=brief_to_out(r.brief, r.stats) if r.brief else None,
        posts=index,
    )
