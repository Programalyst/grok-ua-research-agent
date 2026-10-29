"""Research step: collect X posts for each comparable game (Grok x_search or X API v2), then have the LLM
turn them into a UA brief. Synchronous for the MVP; every paid call is checked against the daily budget
and written to the provider_usage ledger as it happens."""

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.models import Game, ResearchPost, ResearchRun, ResearchStatus, SuggestionStatus, UABrief, XAuthor
from app.providers import CreatorCandidate, LLMProvider, ProviderError, ResearchPostInput
from app.repositories import Repository
from app.services.budget import BudgetExceededError, DailyBudget
from app.x import Collector, CollectTask, XApiError

log = logging.getLogger(__name__)

KEYWORD_BUCKET = "keywords"
MAX_QUERY_LEN = 512  # X recent search query limit (self-serve tiers)
MIN_RESULTS = 10  # X API minimum max_results
MIN_CREATOR_FOLLOWERS = 500
MAX_CREATOR_CANDIDATES = 25

_NEGATIVE = {
    "base": [
        "-is:retweet",
        "-sale",
        "-deal",
        "-deals",
        "-discount",
        "-giveaway",
        "-coupon",
    ],  # "% off" etc. filtered client-side
    "zh": ["-折扣", "-史低", "-特价", "-优惠"],
    "ja": ["-セール", "-割引", "-半額"],
    "ko": ["-할인", "-세일"],
}
_SPAM = re.compile(
    r"(\d+\s?%\s?off|\bsale\b|\bdeals?\b|\bdiscount|\bgiveaway|\bcoupon|\bbundle\b|humble|key\s?giveaway|"
    r"lowest price|price drop|折扣|史低|特价|优惠|セール|割引|半額|할인|세일)",
    re.IGNORECASE,
)
_LANGS = {"en", "zh", "ja", "ko"}
_URL = re.compile(r"https?://\S+")
_NOISE = re.compile(r"[@#]\w+")


@dataclass
class ResearchLimits:
    max_posts_per_comparable: int
    max_posts_total: int
    cost_per_post_usd: float
    batch_size: int = 60
    llm_reserve_usd: float = 0.10
    collector_kind: str = "x_api"  # "x_api" | "grok_x_search"
    max_searches: int = 8  # grok_x_search: one Responses call (with up to N x_search tool calls) per search
    cost_per_search_usd: float = 0.25  # grok_x_search: budgeting estimate per search; actual cost is recorded

    @property
    def max_x_cost_usd(self) -> float:
        if self.collector_kind == "grok_x_search":
            return round(self.max_searches * self.cost_per_search_usd, 4)
        return round(self.max_posts_total * self.cost_per_post_usd, 4)

    @property
    def max_total_cost_usd(self) -> float:
        return round(self.max_x_cost_usd + self.llm_reserve_usd, 4)


@dataclass
class _Collected:
    posts: list[ResearchPost] = field(default_factory=list)
    authors: dict[str, XAuthor] = field(default_factory=dict)
    queries: list[dict] = field(default_factory=list)
    filtered: dict[str, int] = field(default_factory=lambda: {"spam": 0, "links_only": 0, "duplicate": 0})
    returned: int = 0
    stopped: str | None = None  # why collection ended early


def comparables_for(game: Game) -> list[str]:
    names = list(game.comparable_games)
    if game.profile:
        names += [c.name for c in game.profile.suggested_comparables if c.status is not SuggestionStatus.REJECTED]
    return list({n.strip().lower(): n.strip() for n in reversed(names) if n.strip()}.values())[::-1]


def keywords_for(game: Game, lang: str, limit: int = 8) -> list[str]:
    kws = [*game.seed_keywords.get(lang, [])]
    if game.profile:
        kws += game.profile.keywords_by_language.get(lang, [])
    return list(dict.fromkeys(k.strip() for k in kws if k.strip()))[:limit]


def _quote(term: str) -> str:
    term = term.replace('"', "")
    return f'"{term}"' if re.search(r"[\s\-:]", term) else term


def _negatives(lang: str) -> str:
    return " ".join(_NEGATIVE["base"] + _NEGATIVE.get(lang, []))


def comparable_query(name: str, lang: str) -> str:
    exact = name.replace('"', "")
    return f'"{exact}" lang:{lang} {_negatives(lang)}'[:MAX_QUERY_LEN]


def keyword_query(keywords: list[str], lang: str) -> str | None:
    tail = f" lang:{lang} {_negatives(lang)}"
    terms: list[str] = []
    for k in keywords:
        candidate = terms + [_quote(k)]
        if len(f"({' OR '.join(candidate)})") + len(tail) > MAX_QUERY_LEN:
            break
        terms = candidate
    return f"({' OR '.join(terms)}){tail}" if terms else None


def reject_reason(text: str) -> str | None:
    if _SPAM.search(text):
        return "spam"
    if len(_NOISE.sub("", _URL.sub("", text)).strip()) < 12:
        return "links_only"
    return None


def plan_queries(game: Game) -> list[tuple[str, str, str]]:
    """(bucket, language, query) in priority order. Languages rotate per bucket so small caps still spread."""
    langs = list(game.languages) or ["en"]
    plan: list[tuple[str, str, str]] = []
    buckets = comparables_for(game) + [KEYWORD_BUCKET]
    for i, bucket in enumerate(buckets):
        rotated = langs[i % len(langs) :] + langs[: i % len(langs)]
        for lang in rotated:
            q = (
                comparable_query(bucket, lang)
                if bucket != KEYWORD_BUCKET
                else keyword_query(keywords_for(game, lang), lang)
            )
            if q:
                plan.append((bucket, lang, q))
    return plan


def plan_grok_tasks(game: Game, limits: ResearchLimits) -> list[CollectTask]:
    """One search per comparable (multi-language), then language-specific keyword searches. When searches are
    scarce the non-English languages share one combined search so they are never skipped entirely."""
    comps = comparables_for(game)
    other = [lang for lang in (game.languages or ["en"]) if lang != "en"]
    n = limits.max_searches
    n_comps = min(len(comps), n - 1 if other and n > 1 else n)
    left = n - n_comps
    per = limits.max_posts_per_comparable
    tasks = [CollectTask(c, "multi", f'the game "{c}"', per) for c in comps[:n_comps]]
    if left <= 0 or not other:
        return tasks
    about = f"turn-based tactical RPGs like {', '.join(comps[:3]) or game.name}"
    if left >= len(other):
        tasks += [CollectTask(KEYWORD_BUCKET, lang, about, per, keywords_for(game, lang)) for lang in other]
    else:
        terms = [k for lang in other for k in keywords_for(game, lang, 4)]
        tasks.append(CollectTask(KEYWORD_BUCKET, "cjk", about, per, terms))
    return tasks


def plan_tasks(game: Game, limits: ResearchLimits) -> list[CollectTask]:
    if limits.collector_kind == "grok_x_search":
        return plan_grok_tasks(game, limits)
    return [CollectTask(b, lang, q, limits.max_posts_per_comparable) for b, lang, q in plan_queries(game)]


class ResearchService:
    def __init__(
        self, repo: Repository, x: Collector, provider: LLMProvider, budget: DailyBudget, limits: ResearchLimits
    ) -> None:
        self.repo, self.x, self.provider, self.budget, self.limits = repo, x, provider, budget, limits

    def preflight(self) -> None:
        """Refuse to start if the worst-case cost of this run would exceed today's remaining budget."""
        spent = self.budget.spent_usd
        if spent + self.limits.max_total_cost_usd > self.budget.limit_usd:
            raise BudgetExceededError(
                f"Research run could cost up to ${self.limits.max_total_cost_usd:.2f} but only "
                f"${max(0.0, self.budget.limit_usd - spent):.2f} of the "
                f"${self.budget.limit_usd:.2f} daily budget is left; "
                "lower the caps or try tomorrow"
            )

    async def run(self, game: Game) -> ResearchRun:
        self.preflight()
        run = self.repo.add_research_run(
            ResearchRun(
                game_id=game.id,
                provider=self.provider.name,
                x_source=self.x.source,
                max_posts_per_comparable=self.limits.max_posts_per_comparable,
                max_posts_total=self.limits.max_posts_total,
            )
        )
        try:
            col = await self._collect(game, run)
            self.repo.upsert_authors(list(col.authors.values()))
            self.repo.add_research_posts(col.posts)
            run.post_count, run.author_count = len(col.posts), len({p.author_id for p in col.posts})
            run.stats = self._stats(col)
            if col.stopped and col.stopped.startswith("error") and not col.posts:
                raise XApiError(col.stopped.removeprefix("error: "))
            if col.stopped == "budget":
                raise BudgetExceededError("Daily budget reached during collection; run aborted")
            run.brief = await self._analyze(game, run, col) if col.posts else UABrief(summary="No posts found.")
            run.status = ResearchStatus.COMPLETED
        except (XApiError, ProviderError, BudgetExceededError) as e:
            run.status, run.error = ResearchStatus.FAILED, str(e)
            log.warning("research run %s failed: %s", run.id, e)
        run.finished_at = datetime.now(UTC)
        return self.repo.update_research_run(run)

    # ---- collection ---------------------------------------------------------------------------------
    async def _collect(self, game: Game, run: ResearchRun) -> _Collected:
        col = _Collected()
        seen: set[str] = set()
        per_bucket: dict[str, int] = {}
        grok = self.limits.collector_kind == "grok_x_search"
        tasks = plan_tasks(game, self.limits)
        bucket_tasks: dict[str, int] = {}
        for t in tasks:
            bucket_tasks[t.bucket] = bucket_tasks.get(t.bucket, 0) + 1
        done: dict[str, int] = {}
        min_results = 1 if grok else MIN_RESULTS
        for t in tasks:
            done[t.bucket] = done.get(t.bucket, 0) + 1
            bucket_left = self.limits.max_posts_per_comparable - per_bucket.get(t.bucket, 0)
            run_left = self.limits.max_posts_total - col.returned
            left_here = bucket_tasks[t.bucket] - done[t.bucket] + 1
            if grok:
                want = min(bucket_left, run_left)
            else:
                want = min(bucket_left, run_left, max(MIN_RESULTS, math.ceil(bucket_left / left_here)))
            if run_left < min_results:
                col.stopped = col.stopped or "run_cap"
                break
            if want < min_results:
                continue
            est = self.limits.cost_per_search_usd if grok else want * self.limits.cost_per_post_usd
            if self.budget.spent_usd + est > self.budget.limit_usd:
                col.stopped = "budget"
                break
            if run.x_cost_usd + est > self.limits.max_x_cost_usd + 1e-9:
                col.stopped = "cost_cap"
                break
            t.max_posts = want
            entry = {"bucket": t.bucket, "lang": t.lang, "query": t.query, "requested": want}
            try:
                res = await self.x.collect(t)
            except XApiError as e:
                col.queries.append({**entry, "error": str(e)})
                col.stopped = "rate_limited" if e.rate_limited else f"error: {e}"
                break
            returned = res.page.posts[:want]
            col.returned += len(returned)
            per_bucket[t.bucket] = per_bucket.get(t.bucket, 0) + len(returned)
            if res.cost_usd:  # X bills posts read incl. ones we filter; xAI bills the whole call
                self.budget.record(
                    cost_usd=res.cost_usd,
                    provider="xai" if grok else "x",
                    model=res.model,
                    purpose="research_x_search" if grok else "research_x_read",
                    game_id=game.id,
                )
                run.x_cost_usd = round(run.x_cost_usd + res.cost_usd, 6)
            kept = 0
            for p in returned:
                if p.id in seen:
                    col.filtered["duplicate"] += 1
                    continue
                seen.add(p.id)
                if reason := reject_reason(p.text):
                    col.filtered[reason] += 1
                    continue
                kept += 1
                col.posts.append(
                    ResearchPost(
                        run_id=run.id,
                        game_id=game.id,
                        x_id=p.id,
                        comparable=t.bucket,
                        language=p.lang if p.lang not in ("und", "") else (t.lang if t.lang in _LANGS else "und"),
                        text=p.text,
                        author_id=p.author_id,
                        posted_at=p.created_at,
                        query=t.query,
                        likes=p.likes,
                        reposts=p.reposts,
                        replies=p.replies,
                        quotes=p.quotes,
                    )
                )
                if (a := res.page.users.get(p.author_id)) is not None:
                    col.authors[a.id] = a
            col.queries.append(
                {
                    **entry,
                    "returned": len(returned),
                    "kept": kept,
                    "cost_usd": res.cost_usd,
                    **({"collector": res.detail} if res.detail else {}),
                }
            )
        return col

    @staticmethod
    def _cost_split(col: _Collected) -> dict:
        keys = ("search_usd_est", "tokens_usd_est", "x_search_calls", "x_posts_fetched", "reported", "cited")
        out: dict = {k: 0 for k in keys}
        dropped: dict[str, int] = {}
        for q in col.queries:
            d = q.get("collector") or {}
            for k in keys:
                out[k] = round(out[k] + (d.get(k) or 0), 6)
            for k, v in (d.get("dropped") or {}).items():
                dropped[k] = dropped.get(k, 0) + v
        out["dropped"] = dropped
        return out

    def _stats(self, col: _Collected) -> dict:
        by_comp: dict[str, int] = {}
        by_lang: dict[str, int] = {}
        for p in col.posts:
            by_comp[p.comparable] = by_comp.get(p.comparable, 0) + 1
            by_lang[p.language] = by_lang.get(p.language, 0) + 1
        return {
            "posts": len(col.posts),
            "posts_returned": col.returned,
            "queries": col.queries,
            "by_comparable": by_comp,
            "by_language": by_lang,
            "filtered": col.filtered,
            "stopped_early": col.stopped,
            "collector": self.x.source,
            "followers_source": "x_api" if self.x.followers_verified else "grok_reported",
            "collector_cost": self._cost_split(col),
        }

    # ---- analysis -----------------------------------------------------------------------------------
    def _spend_llm(self, run: ResearchRun, cost: float, model: str, purpose: str) -> None:
        self.budget.record(
            cost_usd=cost, provider=self.provider.name, model=model, purpose=purpose, game_id=run.game_id
        )
        run.llm_cost_usd = round(run.llm_cost_usd + (cost or 0.0), 6)

    async def _analyze(self, game: Game, run: ResearchRun, col: _Collected) -> UABrief:
        ordered = sorted(col.posts, key=lambda p: p.engagement, reverse=True)
        ref_to_post = {f"p{i + 1}": p for i, p in enumerate(ordered)}
        x_to_ref = {p.x_id: r for r, p in ref_to_post.items()}
        inputs = [
            ResearchPostInput(
                ref=r,
                comparable=p.comparable,
                language=p.language,
                handle=(col.authors.get(p.author_id) or XAuthor(id="", username="unknown")).username,
                followers=(col.authors.get(p.author_id) or XAuthor(id="", username="")).followers,
                engagement=p.engagement,
                text=p.text,
            )
            for r, p in ref_to_post.items()
        ]
        notes: list[UABrief] = []
        size = max(10, self.limits.batch_size)
        for i in range(0, len(inputs), size):
            self.budget.check()
            n = await self.provider.extract_research_notes(game, inputs[i : i + size])
            self._spend_llm(run, n.cost_usd, n.model, "research_extract")
            notes.append(n)
        creators = self._creator_candidates(col, x_to_ref)
        self.budget.check()
        brief = await self.provider.synthesize_ua_brief(game, notes, creators, run.stats)
        self._spend_llm(run, brief.cost_usd, brief.model, "research_brief")
        brief.cost_usd = run.llm_cost_usd
        return self._resolve_refs(brief, ref_to_post, col.authors)

    def _creator_candidates(self, col: _Collected, x_to_ref: dict[str, str]) -> list[CreatorCandidate]:
        unverified = not self.x.followers_verified  # Grok-reported counts are often missing (0 = unknown)
        by_author: dict[str, list[ResearchPost]] = {}
        for p in col.posts:
            by_author.setdefault(p.author_id, []).append(p)
        cands: list[tuple[float, CreatorCandidate]] = []
        for aid, ps in by_author.items():
            a = col.authors.get(aid)
            if a is None or (a.followers < MIN_CREATOR_FOLLOWERS and not (unverified and a.followers == 0)):
                continue
            top = max(ps, key=lambda p: p.engagement)
            score = (
                math.log10(a.followers + 1) * (1 + 0.5 * (len(ps) - 1)) + math.log10(top.engagement + 1) + 0.1 * len(ps)
            )
            cands.append(
                (
                    score,
                    CreatorCandidate(
                        handle=a.username,
                        followers=a.followers,
                        post_count=len(ps),
                        comparables=sorted({p.comparable for p in ps}),
                        sample_ref=x_to_ref[top.x_id],
                        sample_text=top.text,
                    ),
                )
            )
        return [c for _, c in sorted(cands, key=lambda t: t[0], reverse=True)[:MAX_CREATOR_CANDIDATES]]

    @staticmethod
    def _resolve_refs(brief: UABrief, ref_to_post: dict[str, ResearchPost], authors: dict[str, XAuthor]) -> UABrief:
        """Map model refs (p12) back to real X post ids, dropping any ref the model made up."""

        def ids(refs: list[str]) -> list[str]:
            return list(dict.fromkeys(ref_to_post[r].x_id for r in refs if r in ref_to_post))[:5]

        for ph in brief.player_phrasing:
            ph.example_post_ids = ids(ph.example_post_ids)
        for h in brief.creative_hooks:
            h.evidence_post_ids = ids(h.evidence_post_ids)
        for c in brief.competitor_insights:
            c.example_post_ids = ids(c.example_post_ids)
        for cr in brief.creators:
            p = ref_to_post.get(cr.sample_post_id)
            cr.sample_post_id, cr.sample_text = (p.x_id, p.text) if p else ("", "")
        return brief
