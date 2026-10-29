"""Prompts, JSON schemas and parsers for the research analysis (Grok analyzes ONLY the posts we send; no tools)."""

import json

from app.models import CompetitorInsight, CreativeHook, CreatorPick, Game, PlayerPhrase, UABrief
from app.providers.base import CreatorCandidate, ResearchPostInput

EXTRACT_SYSTEM = """You are a senior game user-acquisition (UA) researcher.
You get a batch of real X posts about games comparable to the developer's game. Analyze ONLY these posts.
Each post line: ref | comparable | lang | @handle (followers) | engagement | text.

Return:
- player_phrasing: phrases players ACTUALLY use (copy them verbatim from the posts, in the post's language;
  genre shorthand, slang, praise/complaint wording). language = ISO code of the phrase. meaning = short English
  gloss. example_post_ids = refs of posts containing it. Skip brand names alone, hashtags of sales, and ad copy.
- competitor_insights: per comparable, concrete complaints and unmet wants players voice (English, short),
  with refs. Only include what the posts support.
- creative_hooks: ad angles worth testing for the developer's game, each tied to one of its differentiators
  and supported by refs (what players love or miss in comparables).
Be specific; no generic marketing filler. Empty lists are fine when the batch has nothing useful."""

SYNTH_SYSTEM = """You are a senior game user-acquisition (UA) strategist writing a UA brief for the developer.
You get: the game's brief, merged research notes extracted from real X posts (refs like p12 point at posts),
and a list of creator candidates with REAL follower counts. Do not invent posts, refs, handles or numbers.

Return:
- summary: 3-5 sentences: what the comparable-game audience talks about, the biggest opening for this game,
  and what to test first.
- player_phrasing: the strongest 4-8 phrases per language present in the notes (dedupe near-duplicates), keep refs.
- creative_hooks: 4-7 distinct ad angles tied to the game's differentiators, each with supporting refs.
- competitor_insights: one entry per comparable that has evidence; merge duplicates; keep refs.
- creators: pick up to 10 candidates by handle that are most relevant for outreach (topic fit beats raw size);
  Skip official game, studio, publisher and store accounts. why = one sentence; sample_post_id = the
  candidate's sample ref."""

_REFS = {"type": "array", "items": {"type": "string"}}
_STR_LIST = {"type": "array", "items": {"type": "string"}}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_PHRASE = _obj(
    {
        "phrase": {"type": "string"},
        "language": {"type": "string"},
        "meaning": {"type": "string"},
        "example_post_ids": _REFS,
    }
)
_HOOK = _obj(
    {
        "title": {"type": "string"},
        "angle": {"type": "string"},
        "differentiator": {"type": "string"},
        "evidence_post_ids": _REFS,
    }
)
_COMP = _obj(
    {"comparable": {"type": "string"}, "complaints": _STR_LIST, "unmet_wants": _STR_LIST, "example_post_ids": _REFS}
)
_CREATOR = _obj({"handle": {"type": "string"}, "why": {"type": "string"}, "sample_post_id": {"type": "string"}})

NOTES_SCHEMA = _obj(
    {
        "player_phrasing": {"type": "array", "items": _PHRASE},
        "competitor_insights": {"type": "array", "items": _COMP},
        "creative_hooks": {"type": "array", "items": _HOOK},
    }
)
BRIEF_SCHEMA = _obj(
    {
        "summary": {"type": "string"},
        "player_phrasing": {"type": "array", "items": _PHRASE},
        "creative_hooks": {"type": "array", "items": _HOOK},
        "competitor_insights": {"type": "array", "items": _COMP},
        "creators": {"type": "array", "items": _CREATOR},
    }
)


def game_context(game: Game) -> str:
    return "\n".join(
        [
            f"Developer's game: {game.name}",
            f"Pitch: {game.pitch or '-'}",
            f"Genres: {', '.join(game.genres) or '-'}",
            f"Differentiators: {(game.differentiators or '-')[:1500]}",
            f"Comparables: {', '.join(game.comparable_games) or '-'}",
        ]
    )


def batch_text(game: Game, posts: list[ResearchPostInput]) -> str:
    lines = [
        f"{p.ref} | {p.comparable} | {p.language} | @{p.handle} ({p.followers}) | {p.engagement} | "
        + " ".join(p.text.split())[:320]
        for p in posts
    ]
    return game_context(game) + f"\n\nPosts ({len(posts)}):\n" + "\n".join(lines)


def synth_text(game: Game, notes: list[UABrief], creators: list[CreatorCandidate], stats: dict) -> str:
    merged = {
        "player_phrasing": [p.__dict__ for n in notes for p in n.player_phrasing],
        "competitor_insights": [c.__dict__ for n in notes for c in n.competitor_insights],
        "creative_hooks": [h.__dict__ for n in notes for h in n.creative_hooks],
    }
    cands = [
        {
            "handle": c.handle,
            "followers": c.followers,
            "posts": c.post_count,
            "comparables": c.comparables,
            "sample_ref": c.sample_ref,
            "sample": " ".join(c.sample_text.split())[:200],
        }
        for c in creators
    ]
    stats_line = {k: stats[k] for k in ("posts", "by_comparable", "by_language") if k in stats}
    return (
        game_context(game)
        + f"\n\nCollection stats: {json.dumps(stats_line, ensure_ascii=False)}"
        + f"\n\nResearch notes:\n{json.dumps(merged, ensure_ascii=False)}"
        + f"\n\nCreator candidates:\n{json.dumps(cands, ensure_ascii=False)}"
    )


def notes_from(d: dict) -> UABrief:
    return UABrief(
        player_phrasing=[PlayerPhrase(**x) for x in d.get("player_phrasing", [])],
        creative_hooks=[CreativeHook(**x) for x in d.get("creative_hooks", [])],
        competitor_insights=[CompetitorInsight(**x) for x in d.get("competitor_insights", [])],
    )


def brief_from(d: dict, creators: list[CreatorCandidate]) -> UABrief:
    b = notes_from(d)
    b.summary = str(d.get("summary", "")).strip()
    by_handle = {c.handle.lower(): c for c in creators}
    for x in d.get("creators", []):
        c = by_handle.get(str(x.get("handle", "")).lstrip("@").lower())
        if c is None:  # model may only pick from the candidates
            continue
        b.creators.append(
            CreatorPick(
                handle=c.handle,
                followers=c.followers,
                why=str(x.get("why", "")).strip(),
                sample_post_id=c.sample_ref,
                sample_text=c.sample_text,
            )
        )
    return b
