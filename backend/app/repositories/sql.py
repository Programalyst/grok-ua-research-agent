"""SQL repository (SQLAlchemy Core). Works on SQLite locally and Postgres (e.g. Supabase).

Domain dataclasses stay framework-free; rows are mapped explicitly in the _to_*/_from_* helpers.
The Game aggregate (brief + images + profile) is saved atomically by add_game/update_game.
"""

from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import Engine, delete, func, insert, select, update
from sqlalchemy.engine import Connection, RowMapping

from app.db.tables import (
    game_profiles,
    games,
    images,
    posts,
    provider_usage,
    research_posts,
    research_runs,
    scans,
    x_authors,
)
from app.models import (
    Category,
    Game,
    GameImage,
    GameProfile,
    ImageKind,
    Platform,
    Post,
    ResearchPost,
    ResearchRun,
    ResearchStatus,
    Scan,
    ScanStatus,
    Sentiment,
    SuggestedComparable,
    SuggestionStatus,
    UsageRecord,
    XAuthor,
)
from app.models.research import brief_from_dict, brief_to_dict


def _utc(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; values are always written as UTC so re-attach it."""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


# ---- row <-> dataclass mappers -------------------------------------------------------------------


def _game_row(g: Game) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "pitch": g.pitch,
        "description": g.description,
        "differentiators": g.differentiators,
        "genres": list(g.genres),
        "platforms": [p.value for p in g.platforms],
        "regions": list(g.regions),
        "languages": list(g.languages),
        "comparable_games": list(g.comparable_games),
        "seed_keywords": {k: list(v) for k, v in g.seed_keywords.items()},
        "keywords": list(g.keywords),
        "hashtags": list(g.hashtags),
        "handles": list(g.handles),
        "created_at": g.created_at,
        "updated_at": datetime.now(UTC),
    }


def _game_from(r: RowMapping, imgs: list[GameImage], profile: GameProfile | None) -> Game:
    return Game(
        id=r["id"],
        name=r["name"],
        pitch=r["pitch"],
        description=r["description"],
        differentiators=r["differentiators"],
        genres=list(r["genres"]),
        platforms=[Platform(p) for p in r["platforms"]],
        regions=list(r["regions"]),
        languages=list(r["languages"]),
        comparable_games=list(r["comparable_games"]),
        seed_keywords={k: list(v) for k, v in (r["seed_keywords"] or {}).items()},
        keywords=list(r["keywords"]),
        hashtags=list(r["hashtags"]),
        handles=list(r["handles"]),
        images=imgs,
        profile=profile,
        created_at=_utc(r["created_at"]),
    )


def _image_row(i: GameImage) -> dict:
    return {
        "id": i.id,
        "game_id": i.game_id,
        "kind": i.kind.value,
        "filename": i.filename,
        "content_type": i.content_type,
        "size_bytes": i.size_bytes,
        "width": i.width,
        "height": i.height,
        "stored_name": i.stored_name,
        "created_at": i.created_at,
    }


def _image_from(r: RowMapping) -> GameImage:
    return GameImage(
        id=r["id"],
        game_id=r["game_id"],
        kind=ImageKind(r["kind"]),
        filename=r["filename"],
        content_type=r["content_type"],
        size_bytes=r["size_bytes"],
        width=r["width"],
        height=r["height"],
        stored_name=r["stored_name"],
        created_at=_utc(r["created_at"]),
    )


def _profile_row(p: GameProfile) -> dict:
    return {
        "game_id": p.game_id,
        "themes": list(p.themes),
        "keywords_by_language": {k: list(v) for k, v in p.keywords_by_language.items()},
        "suggested_comparables": [
            {"name": c.name, "reason": c.reason, "status": c.status.value} for c in p.suggested_comparables
        ],
        "visual_style": list(p.visual_style),
        "target_audience": p.target_audience,
        "generated_by": p.generated_by,
        "model": p.model,
        "cost_usd": p.cost_usd,
        "edited": p.edited,
        "updated_at": p.updated_at,
    }


def _profile_from(r: RowMapping) -> GameProfile:
    return GameProfile(
        game_id=r["game_id"],
        themes=list(r["themes"]),
        keywords_by_language={k: list(v) for k, v in r["keywords_by_language"].items()},
        suggested_comparables=[
            SuggestedComparable(name=c["name"], reason=c.get("reason", ""), status=SuggestionStatus(c["status"]))
            for c in r["suggested_comparables"]
        ],
        visual_style=list(r["visual_style"]),
        target_audience=r["target_audience"],
        generated_by=r["generated_by"],
        model=r["model"],
        cost_usd=r["cost_usd"],
        edited=r["edited"],
        updated_at=_utc(r["updated_at"]),
    )


def _scan_row(s: Scan) -> dict:
    d = asdict(s)
    d["status"] = s.status.value
    return d


def _scan_from(r: RowMapping) -> Scan:
    return Scan(
        id=r["id"],
        game_id=r["game_id"],
        provider=r["provider"],
        status=ScanStatus(r["status"]),
        post_count=r["post_count"],
        error=r["error"],
        started_at=_utc(r["started_at"]),
        finished_at=_utc(r["finished_at"]),
    )


def _post_row(p: Post) -> dict:
    d = asdict(p)
    d["sentiment"], d["category"] = p.sentiment.value, p.category.value
    return d


def _post_from(r: RowMapping) -> Post:
    return Post(
        id=r["id"],
        game_id=r["game_id"],
        scan_id=r["scan_id"],
        text=r["text"],
        author=r["author"],
        language=r["language"],
        sentiment=Sentiment(r["sentiment"]),
        category=Category(r["category"]),
        url=r["url"],
        posted_at=_utc(r["posted_at"]),
        likes=r["likes"],
        reposts=r["reposts"],
        replies=r["replies"],
        author_followers=r["author_followers"],
    )


# ---- repository ----------------------------------------------------------------------------------


def _run_row(r: ResearchRun) -> dict:
    d = {k: v for k, v in asdict(r).items() if k != "brief"}
    d["status"] = r.status.value
    d["brief"] = brief_to_dict(r.brief) if r.brief else None
    return d


def _run_from(r: RowMapping) -> ResearchRun:
    return ResearchRun(
        game_id=r["game_id"],
        provider=r["provider"],
        x_source=r["x_source"],
        max_posts_per_comparable=r["max_posts_per_comparable"],
        max_posts_total=r["max_posts_total"],
        status=ResearchStatus(r["status"]),
        post_count=r["post_count"],
        author_count=r["author_count"],
        stats=r["stats"] or {},
        x_cost_usd=r["x_cost_usd"],
        llm_cost_usd=r["llm_cost_usd"],
        brief=brief_from_dict(r["brief"]) if r["brief"] else None,
        error=r["error"],
        id=r["id"],
        started_at=_utc(r["started_at"]),
        finished_at=_utc(r["finished_at"]),
    )


def _rpost_from(r: RowMapping) -> ResearchPost:
    d = dict(r)
    d["posted_at"] = _utc(d["posted_at"])
    return ResearchPost(**d)


def _author_from(r: RowMapping) -> XAuthor:
    d = dict(r)
    d["updated_at"] = _utc(d["updated_at"])
    return XAuthor(**d)


class SqlRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # games (aggregate: brief + images + profile)
    def _load_games(self, conn: Connection, game_ids: list[str] | None) -> list[Game]:
        q = select(games).order_by(games.c.created_at)
        if game_ids is not None:
            q = q.where(games.c.id.in_(game_ids))
        rows = conn.execute(q).mappings().all()
        ids = [r["id"] for r in rows]
        if not ids:
            return []
        imgs: dict[str, list[GameImage]] = {}
        for r in conn.execute(select(images).where(images.c.game_id.in_(ids)).order_by(images.c.created_at)).mappings():
            imgs.setdefault(r["game_id"], []).append(_image_from(r))
        profs = {
            r["game_id"]: _profile_from(r)
            for r in conn.execute(select(game_profiles).where(game_profiles.c.game_id.in_(ids))).mappings()
        }
        return [_game_from(r, imgs.get(r["id"], []), profs.get(r["id"])) for r in rows]

    def _save_game(self, conn: Connection, game: Game) -> None:
        row = _game_row(game)
        exists = conn.execute(select(games.c.id).where(games.c.id == game.id)).first()
        if exists:
            conn.execute(update(games).where(games.c.id == game.id).values(**row))
        else:
            conn.execute(insert(games).values(**row))

        current = set(conn.scalars(select(images.c.id).where(images.c.game_id == game.id)))
        wanted = {i.id: i for i in game.images}
        if stale := current - wanted.keys():
            conn.execute(delete(images).where(images.c.id.in_(stale)))
        for img_id, img in wanted.items():
            if img_id in current:
                conn.execute(update(images).where(images.c.id == img_id).values(**_image_row(img)))
            else:
                conn.execute(insert(images).values(**_image_row(img)))

        conn.execute(delete(game_profiles).where(game_profiles.c.game_id == game.id))
        if game.profile is not None:
            conn.execute(insert(game_profiles).values(**_profile_row(game.profile)))

    def add_game(self, game: Game) -> Game:
        with self.engine.begin() as conn:
            self._save_game(conn, game)
        return game

    def update_game(self, game: Game) -> Game:
        return self.add_game(game)

    def get_game(self, game_id: str) -> Game | None:
        with self.engine.connect() as conn:
            found = self._load_games(conn, [game_id])
        return found[0] if found else None

    def list_games(self) -> list[Game]:
        with self.engine.connect() as conn:
            return self._load_games(conn, None)

    def delete_game(self, game_id: str) -> bool:
        # Explicit child deletes so behavior doesn't depend on FK cascade being enabled.
        with self.engine.begin() as conn:
            conn.execute(delete(research_posts).where(research_posts.c.game_id == game_id))
            conn.execute(delete(research_runs).where(research_runs.c.game_id == game_id))
            conn.execute(delete(posts).where(posts.c.game_id == game_id))
            conn.execute(delete(scans).where(scans.c.game_id == game_id))
            conn.execute(delete(images).where(images.c.game_id == game_id))
            conn.execute(delete(game_profiles).where(game_profiles.c.game_id == game_id))
            conn.execute(update(provider_usage).where(provider_usage.c.game_id == game_id).values(game_id=None))
            return conn.execute(delete(games).where(games.c.id == game_id)).rowcount > 0

    # scans
    def add_scan(self, scan: Scan) -> Scan:
        with self.engine.begin() as conn:
            conn.execute(insert(scans).values(**_scan_row(scan)))
        return scan

    def update_scan(self, scan: Scan) -> Scan:
        with self.engine.begin() as conn:
            conn.execute(update(scans).where(scans.c.id == scan.id).values(**_scan_row(scan)))
        return scan

    def get_scan(self, scan_id: str) -> Scan | None:
        with self.engine.connect() as conn:
            r = conn.execute(select(scans).where(scans.c.id == scan_id)).mappings().first()
        return _scan_from(r) if r else None

    def list_scans(self, game_id: str) -> list[Scan]:
        q = select(scans).where(scans.c.game_id == game_id).order_by(scans.c.started_at.desc())
        with self.engine.connect() as conn:
            return [_scan_from(r) for r in conn.execute(q).mappings()]

    # posts
    def add_posts(self, items: list[Post]) -> None:
        if not items:
            return
        with self.engine.begin() as conn:
            conn.execute(insert(posts), [_post_row(p) for p in items])

    def list_posts(self, game_id: str) -> list[Post]:
        q = select(posts).where(posts.c.game_id == game_id).order_by(posts.c.posted_at.desc())
        with self.engine.connect() as conn:
            return [_post_from(r) for r in conn.execute(q).mappings()]

    # provider usage / cost ledger
    def add_usage(self, record: UsageRecord) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(provider_usage).values(**asdict(record)))

    def usage_cost_since(self, since: datetime) -> float:
        q = select(func.coalesce(func.sum(provider_usage.c.cost_usd), 0.0)).where(provider_usage.c.created_at >= since)
        with self.engine.connect() as conn:
            return float(conn.scalar(q) or 0.0)

    # research
    def add_research_run(self, run: ResearchRun) -> ResearchRun:
        with self.engine.begin() as conn:
            conn.execute(insert(research_runs).values(**_run_row(run)))
        return run

    def update_research_run(self, run: ResearchRun) -> ResearchRun:
        with self.engine.begin() as conn:
            conn.execute(update(research_runs).where(research_runs.c.id == run.id).values(**_run_row(run)))
        return run

    def get_research_run(self, run_id: str) -> ResearchRun | None:
        with self.engine.connect() as conn:
            r = conn.execute(select(research_runs).where(research_runs.c.id == run_id)).mappings().first()
        return _run_from(r) if r else None

    def list_research_runs(self, game_id: str) -> list[ResearchRun]:
        q = select(research_runs).where(research_runs.c.game_id == game_id).order_by(research_runs.c.started_at.desc())
        with self.engine.connect() as conn:
            return [_run_from(r) for r in conn.execute(q).mappings()]

    def add_research_posts(self, items: list[ResearchPost]) -> None:
        if not items:
            return
        with self.engine.begin() as conn:
            conn.execute(insert(research_posts), [asdict(p) for p in items])

    def list_research_posts(self, run_id: str) -> list[ResearchPost]:
        q = select(research_posts).where(research_posts.c.run_id == run_id).order_by(research_posts.c.posted_at)
        with self.engine.connect() as conn:
            return [_rpost_from(r) for r in conn.execute(q).mappings()]

    def upsert_authors(self, authors: list[XAuthor]) -> None:
        if not authors:
            return
        with self.engine.begin() as conn:
            existing = set(conn.scalars(select(x_authors.c.id).where(x_authors.c.id.in_([a.id for a in authors]))))
            for a in authors:
                row = asdict(a)
                if a.id in existing:
                    conn.execute(update(x_authors).where(x_authors.c.id == a.id).values(**row))
                else:
                    conn.execute(insert(x_authors).values(**row))
                    existing.add(a.id)

    def get_authors(self, author_ids: list[str]) -> dict[str, XAuthor]:
        if not author_ids:
            return {}
        with self.engine.connect() as conn:
            rows = conn.execute(select(x_authors).where(x_authors.c.id.in_(list(set(author_ids))))).mappings()
            return {r["id"]: _author_from(r) for r in rows}
