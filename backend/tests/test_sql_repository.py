"""SqlRepository round-trips on a migrated temp SQLite DB (same schema Postgres would get)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.db import make_engine
from app.db.migrate import upgrade_to_head
from app.models import (
    Category,
    Game,
    GameImage,
    GameProfile,
    ImageKind,
    Platform,
    Post,
    Scan,
    ScanStatus,
    Sentiment,
    SuggestedComparable,
    SuggestionStatus,
    UsageRecord,
)
from app.repositories import SqlRepository


@pytest.fixture
def sql_repo(tmp_path):
    url = f"sqlite:///{tmp_path / 'r.db'}"
    upgrade_to_head(url)
    return SqlRepository(make_engine(url))


def _game() -> Game:
    g = Game(
        name="Ashfall",
        description="d" * 5000,
        platforms=[Platform.PC],
        languages=["en", "zh"],
        seed_keywords={"zh": ["战棋", "末日"]},
    )
    g.images.append(GameImage(g.id, "a.png", "image/png", 10, "a.png", kind=ImageKind.KEY_ART, width=4, height=3))
    g.profile = GameProfile(
        g.id,
        themes=["t"],
        keywords_by_language={"zh": ["废土"]},
        suggested_comparables=[SuggestedComparable("XCOM 2", "r", SuggestionStatus.ACCEPTED)],
        model="grok-4.3",
        cost_usd=0.004,
    )
    return g


def test_game_aggregate_round_trip(sql_repo):
    g = sql_repo.add_game(_game())
    got = sql_repo.get_game(g.id)
    assert got == g  # dataclass equality: every field incl. images/profile/tz-aware timestamps
    assert got.created_at.tzinfo is not None

    got.images = []
    got.profile = None
    got.name = "Renamed"
    sql_repo.update_game(got)
    again = sql_repo.get_game(g.id)
    assert again.name == "Renamed" and again.images == [] and again.profile is None
    assert [x.id for x in sql_repo.list_games()] == [g.id]


def test_scans_posts_usage_and_delete(sql_repo):
    g = sql_repo.add_game(_game())
    scan = sql_repo.add_scan(Scan(game_id=g.id, provider="fake"))
    scan.status, scan.finished_at = ScanStatus.COMPLETED, datetime.now(UTC)
    sql_repo.update_scan(scan)
    assert sql_repo.get_scan(scan.id) == scan and sql_repo.list_scans(g.id) == [scan]
    p = Post(g.id, scan.id, "gg", "a", "en", Sentiment.POSITIVE, Category.PRAISE, "u", datetime.now(UTC), likes=3)
    sql_repo.add_posts([p])
    assert sql_repo.list_posts(g.id) == [p]

    sql_repo.add_usage(UsageRecord("profile_generation", "grok", "grok-4.3", 0.01, game_id=g.id))
    old = UsageRecord("x", "grok", "grok-4.3", 5.0, created_at=datetime.now(UTC) - timedelta(days=2))
    sql_repo.add_usage(old)
    assert sql_repo.usage_cost_since(datetime.now(UTC) - timedelta(hours=1)) == pytest.approx(0.01)

    assert sql_repo.delete_game(g.id) is True
    assert sql_repo.get_game(g.id) is None and sql_repo.list_posts(g.id) == [] and sql_repo.list_scans(g.id) == []
    assert sql_repo.usage_cost_since(datetime.now(UTC) - timedelta(hours=1)) == pytest.approx(0.01)  # ledger kept


def test_data_survives_new_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'p.db'}"
    upgrade_to_head(url)
    g = SqlRepository(make_engine(url)).add_game(_game())
    upgrade_to_head(url)  # idempotent
    assert SqlRepository(make_engine(url)).get_game(g.id) == g
