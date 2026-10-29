"""SQLAlchemy Core tables (Postgres-compatible). Rows are mapped to/from dataclasses in SqlRepository."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

ID = String(32)  # uuid4 hex; maps cleanly to text/uuid in Postgres
TS = DateTime(timezone=True)

games = Table(
    "games",
    metadata,
    Column("id", ID, primary_key=True),
    Column("name", String(200), nullable=False),
    Column("pitch", String(280), nullable=False, default=""),
    Column("description", Text, nullable=False, default=""),
    Column("differentiators", Text, nullable=False, default=""),
    Column("genres", JSON, nullable=False),
    Column("platforms", JSON, nullable=False),
    Column("regions", JSON, nullable=False),
    Column("languages", JSON, nullable=False),
    Column("comparable_games", JSON, nullable=False),
    Column("seed_keywords", JSON, nullable=False),
    Column("keywords", JSON, nullable=False),
    Column("hashtags", JSON, nullable=False),
    Column("handles", JSON, nullable=False),
    Column("created_at", TS, nullable=False),
    Column("updated_at", TS, nullable=False),
)

images = Table(
    "images",
    metadata,
    Column("id", ID, primary_key=True),
    Column("game_id", ID, ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("kind", String(16), nullable=False),
    Column("filename", String(200), nullable=False),
    Column("content_type", String(50), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("width", Integer, nullable=False),
    Column("height", Integer, nullable=False),
    Column("stored_name", String(100), nullable=False),
    Column("created_at", TS, nullable=False),
)

game_profiles = Table(
    "game_profiles",
    metadata,
    Column("game_id", ID, ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("themes", JSON, nullable=False),
    Column("keywords_by_language", JSON, nullable=False),
    Column("suggested_comparables", JSON, nullable=False),
    Column("visual_style", JSON, nullable=False),
    Column("target_audience", Text, nullable=False),
    Column("generated_by", String(50), nullable=False),
    Column("model", String(100), nullable=False),
    Column("cost_usd", Float, nullable=True),
    Column("edited", Boolean, nullable=False),
    Column("updated_at", TS, nullable=False),
)

scans = Table(
    "scans",
    metadata,
    Column("id", ID, primary_key=True),
    Column("game_id", ID, ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("provider", String(50), nullable=False),
    Column("status", String(16), nullable=False),
    Column("post_count", Integer, nullable=False),
    Column("error", Text, nullable=True),
    Column("started_at", TS, nullable=False),
    Column("finished_at", TS, nullable=True),
)

posts = Table(
    "posts",
    metadata,
    Column("id", ID, primary_key=True),
    Column("game_id", ID, ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
    Column("scan_id", ID, ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("text", Text, nullable=False),
    Column("author", String(200), nullable=False),
    Column("language", String(10), nullable=False),
    Column("sentiment", String(16), nullable=False),
    Column("category", String(16), nullable=False),
    Column("url", Text, nullable=False),
    Column("posted_at", TS, nullable=False),
    Column("likes", Integer, nullable=False),
    Column("reposts", Integer, nullable=False),
    Column("replies", Integer, nullable=False),
    Column("author_followers", Integer, nullable=False),
    Index("ix_posts_game_id_posted_at", "game_id", "posted_at"),
)

provider_usage = Table(
    "provider_usage",
    metadata,
    Column("id", ID, primary_key=True),
    Column("game_id", ID, ForeignKey("games.id", ondelete="SET NULL"), nullable=True, index=True),
    Column("purpose", String(50), nullable=False),
    Column("provider", String(50), nullable=False),
    Column("model", String(100), nullable=False),
    Column("cost_usd", Float, nullable=False),
    Column("created_at", TS, nullable=False, index=True),
)


research_runs = Table(
    "research_runs",
    metadata,
    Column("id", ID, primary_key=True),
    Column("game_id", ID, ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("provider", String(50), nullable=False),
    Column("x_source", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("max_posts_per_comparable", Integer, nullable=False),
    Column("max_posts_total", Integer, nullable=False),
    Column("post_count", Integer, nullable=False, default=0),
    Column("author_count", Integer, nullable=False, default=0),
    Column("stats", JSON, nullable=False),
    Column("x_cost_usd", Float, nullable=False, default=0.0),
    Column("llm_cost_usd", Float, nullable=False, default=0.0),
    Column("brief", JSON, nullable=True),  # UABrief as JSON (sections are read together, never queried apart)
    Column("error", Text, nullable=True),
    Column("started_at", TS, nullable=False),
    Column("finished_at", TS, nullable=True),
)

# X accounts, shared across runs/games (latest follower count wins).
x_authors = Table(
    "x_authors",
    metadata,
    Column("id", String(32), primary_key=True),  # X user id
    Column("username", String(50), nullable=False, index=True),
    Column("name", String(200), nullable=False, default=""),
    Column("followers", Integer, nullable=False, default=0),
    Column("verified", Boolean, nullable=False, default=False),
    Column("description", Text, nullable=False, default=""),
    Column("updated_at", TS, nullable=False),
)

# Normalized columns (comparable, language, posted_at, metrics) so analytics stay plain SQL.
research_posts = Table(
    "research_posts",
    metadata,
    Column("id", ID, primary_key=True),
    Column("run_id", ID, ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("game_id", ID, ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
    Column("x_id", String(32), nullable=False),
    Column("comparable", String(200), nullable=False),
    Column("language", String(10), nullable=False),
    Column("text", Text, nullable=False),
    Column("author_id", String(32), nullable=False, index=True),
    Column("posted_at", TS, nullable=False),
    Column("query", Text, nullable=False, default=""),
    Column("likes", Integer, nullable=False, default=0),
    Column("reposts", Integer, nullable=False, default=0),
    Column("replies", Integer, nullable=False, default=0),
    Column("quotes", Integer, nullable=False, default=0),
    UniqueConstraint("run_id", "x_id", name="uq_research_posts_run_x"),
    Index("ix_research_posts_game_comparable", "game_id", "comparable"),
)
