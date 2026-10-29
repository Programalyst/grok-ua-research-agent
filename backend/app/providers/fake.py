"""Deterministic provider so the app runs with no API key."""

import random
from datetime import UTC, datetime, timedelta

from app.models import (
    Category,
    CompetitorInsight,
    CreativeHook,
    CreatorPick,
    Game,
    GameProfile,
    PlayerPhrase,
    Sentiment,
    SuggestedComparable,
    UABrief,
)
from app.providers.base import CreatorCandidate, ImageInput, RawClassifiedPost, ResearchPostInput

_SAMPLES: list[tuple[str, str, Sentiment, Category]] = [
    ("en", "Just finished the tutorial of {g}, the combat feels amazing!", Sentiment.POSITIVE, Category.PRAISE),
    ("en", "{g} crashes on launch on my RTX 3070, anyone else?", Sentiment.NEGATIVE, Category.BUG),
    ("en", "Does {g} support cross-save between PC and console?", Sentiment.NEUTRAL, Category.QUESTION),
    ("ja", "{g}のグラフィックが最高すぎる", Sentiment.POSITIVE, Category.PRAISE),
    ("ja", "{g} ログインできない…サーバー落ちてる？", Sentiment.NEGATIVE, Category.BUG),
    ("ko", "{g} 오늘 출시! 기대됩니다", Sentiment.POSITIVE, Category.PRAISE),
    ("ko", "{g} 매칭이 너무 오래 걸려요", Sentiment.NEGATIVE, Category.BUG),
    ("zh", "{g} 的剧情太好了，强烈推荐", Sentiment.POSITIVE, Category.PRAISE),
    ("zh", "{g} 有中文配音吗？", Sentiment.NEUTRAL, Category.QUESTION),
    ("en", "Streaming {g} launch day live right now with 50k viewers!", Sentiment.POSITIVE, Category.INFLUENCER),
]


# Small genre -> (themes, en keywords, comparables, visual style) table for deterministic output.
_GENRE_HINTS: dict[str, tuple[list[str], list[str], list[str], list[str]]] = {
    "roguelike": (
        ["run-based mastery", "build crafting"],
        ["one more run", "broken build", "synergy"],
        ["Hades", "Slay the Spire"],
        ["readable silhouettes"],
    ),
    "rpg": (
        ["character progression", "story choices"],
        ["build", "lore", "party comp"],
        ["Baldur's Gate 3", "Genshin Impact"],
        ["painterly fantasy"],
    ),
    "gacha": (
        ["collection", "banner hype"],
        ["pulls", "pity", "banner", "f2p friendly"],
        ["Genshin Impact", "Honkai: Star Rail"],
        ["anime cel-shaded"],
    ),
    "shooter": (
        ["gunplay feel", "competitive mastery"],
        ["ttk", "aim", "ranked", "meta"],
        ["Valorant", "Apex Legends"],
        ["high-contrast effects"],
    ),
    "cozy": (
        ["relaxation", "creativity"],
        ["cozy", "wholesome", "chill vibes"],
        ["Stardew Valley", "Animal Crossing"],
        ["soft pastel palette"],
    ),
    "strategy": (
        ["planning", "outsmarting opponents"],
        ["meta", "tier list", "build order"],
        ["Into the Breach", "Civilization VI"],
        ["clean top-down UI"],
    ),
}
_COMPLAINT_MARKERS = ("wish", "rng", "repetitive", "miss", "后期", "太少", "命中率", "지루")

_LANG_KEYWORDS: dict[str, list[str]] = {
    "en": ["gameplay", "worth it", "review"],
    "ja": ["神ゲー", "攻略", "実況"],
    "ko": ["꿀잼", "공략", "리뷰"],
    "zh": ["好玩", "攻略", "测评"],
}


class FakeProvider:
    name = "fake"

    def __init__(self, seed: int = 42, now: datetime | None = None) -> None:
        self._seed = seed
        self._now = now

    async def search_and_classify(self, game: Game, max_posts: int) -> list[RawClassifiedPost]:
        rng = random.Random(f"{self._seed}:{game.name}")
        now = self._now or datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        samples = [s for s in _SAMPLES if s[0] in game.languages] or _SAMPLES
        out: list[RawClassifiedPost] = []
        for i in range(max_posts):
            lang, tmpl, sentiment, category = samples[i % len(samples)]
            influencer = category is Category.INFLUENCER
            followers = rng.randint(200_000, 2_000_000) if influencer else rng.randint(10, 5_000)
            likes = rng.randint(5_000, 50_000) if influencer else rng.randint(0, 300)
            out.append(
                RawClassifiedPost(
                    text=tmpl.format(g=game.name),
                    author=f"user_{lang}_{i}",
                    language=lang,
                    sentiment=sentiment,
                    category=category,
                    url=f"https://x.com/user_{lang}_{i}/status/{1_800_000_000_000_000_000 + i}",
                    posted_at=now - timedelta(hours=i % 12, minutes=rng.randint(0, 59)),
                    likes=likes,
                    reposts=likes // 10,
                    replies=likes // 20,
                    author_followers=followers,
                )
            )
        return out

    async def generate_profile(self, game: Game, images: list[ImageInput]) -> GameProfile:
        genres = [g.lower() for g in game.genres]
        hints = [_GENRE_HINTS[g] for g in genres if g in _GENRE_HINTS]
        themes = [t for h in hints for t in h[0]] or [f"{g} fans" for g in genres] or ["core gameplay loop"]
        if game.differentiators:
            themes.append(game.differentiators.split(".")[0].strip()[:80])
        en_kw = [game.name.lower(), *[g.lower() for g in game.genres], *[k for h in hints for k in h[1]]]
        keywords = {}
        for lang in game.languages:
            base = en_kw if lang == "en" else [game.name]
            keywords[lang] = list(
                dict.fromkeys([*game.seed_keywords.get(lang, []), *base, *_LANG_KEYWORDS.get(lang, [])])
            )
        existing = {c.lower() for c in game.comparable_games} | {game.name.lower()}
        suggestions = [
            SuggestedComparable(
                name=c, reason=f"Popular {genres[i] if i < len(genres) else 'genre'} title with an overlapping audience"
            )
            for i, h in enumerate(hints)
            for c in h[2]
            if c.lower() not in existing
        ][:4] or [SuggestedComparable(name="Hades", reason="Widely referenced indie hit (placeholder)")]
        visual = [v for h in hints for v in h[3]] + (
            [f"{len(images)} uploaded visual(s) - style analysis needs a real vision model"] if images else []
        )
        platforms = ", ".join(p.value for p in game.platforms) or "unspecified platforms"
        regions = ", ".join(game.regions) or "global"
        audience = (
            f"Players of {', '.join(game.comparable_games[:3]) or 'similar games'} on {platforms} "
            f"in {regions}, drawn to: {game.pitch or game.name}."
        )
        return GameProfile(
            game_id=game.id,
            themes=list(dict.fromkeys(themes)),
            keywords_by_language=keywords,
            suggested_comparables=suggestions,
            visual_style=visual or ["(no style hints)"],
            target_audience=audience,
            generated_by=self.name,
            model="fake",
            cost_usd=0.0,
        )

    async def extract_research_notes(self, game: Game, posts: list[ResearchPostInput]) -> UABrief:
        phrases: dict[tuple[str, str], list[str]] = {}
        complaints: dict[str, CompetitorInsight] = {}
        for p in posts:
            phrase = " ".join(p.text.split()[1:4]) if p.language == "en" else p.text.split()[-1][:12]
            phrases.setdefault((phrase, p.language), []).append(p.ref)
            if any(m in p.text.lower() for m in _COMPLAINT_MARKERS):
                ci = complaints.setdefault(p.comparable, CompetitorInsight(comparable=p.comparable))
                ci.complaints = list(dict.fromkeys([*ci.complaints, p.text[:80]]))[:3]
                ci.example_post_ids.append(p.ref)
        diff = (game.differentiators or game.pitch or game.name).split(".")[0][:80]
        return UABrief(
            player_phrasing=[
                PlayerPhrase(phrase=ph, language=lang, example_post_ids=refs[:3])
                for (ph, lang), refs in phrases.items()
            ][:12],
            creative_hooks=[
                CreativeHook(title="Fix what they miss", angle="Answer top complaints", differentiator=diff)
            ],
            competitor_insights=list(complaints.values()),
            model="fake",
        )

    async def synthesize_ua_brief(
        self, game: Game, notes: list[UABrief], creators: list[CreatorCandidate], stats: dict
    ) -> UABrief:
        merged = UABrief(model="fake")
        by_comp: dict[str, CompetitorInsight] = {}
        for n in notes:
            merged.player_phrasing += n.player_phrasing
            merged.creative_hooks += [
                h for h in n.creative_hooks if h.title not in {x.title for x in merged.creative_hooks}
            ]
            for ci in n.competitor_insights:
                cur = by_comp.setdefault(ci.comparable, CompetitorInsight(comparable=ci.comparable))
                cur.complaints = list(dict.fromkeys([*cur.complaints, *ci.complaints]))[:5]
                cur.example_post_ids += ci.example_post_ids
        merged.competitor_insights = list(by_comp.values())
        merged.creators = [
            CreatorPick(
                handle=c.handle,
                followers=c.followers,
                why=f"Posts about {', '.join(c.comparables)}",
                sample_post_id=c.sample_ref,
            )
            for c in creators[:5]
        ]
        merged.summary = (
            f"Fake analysis of {stats.get('posts', 0)} posts for {game.name}: "
            f"{len(merged.player_phrasing)} phrases, {len(merged.competitor_insights)} comparables with complaints."
        )
        return merged
