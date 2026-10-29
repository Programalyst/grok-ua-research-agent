from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Game Launch Monitor"
    xai_api_key: str | None = None
    xai_base_url: str = "https://api.x.ai/v1"
    # grok-4.3: cheapest current Grok with image input + structured outputs ($1.25/M in, $2.50/M out)
    xai_model: str = "grok-4.3"
    xai_reasoning_effort: str = "low"
    xai_timeout_seconds: float = 90.0
    x_bearer_token: str | None = None  # X API v2 app-only bearer (read-only recent search)
    x_api_base_url: str = "https://api.x.com/2"
    x_timeout_seconds: float = 20.0
    x_cost_per_post_usd: float = 0.005  # estimate: $5 per 1k posts read
    research_max_posts_per_comparable: int = 50
    research_max_posts_per_run: int = 400
    research_batch_size: int = 60  # posts per Grok extraction call
    research_llm_reserve_usd: float = 0.10
    # Collector: "grok_x_search" (xAI x_search tool, billed to the xAI balance) or "x_api" (X API bearer token)
    research_collector: Literal["grok_x_search", "x_api"] = "grok_x_search"
    research_max_searches: int = 8  # grok_x_search: Responses calls per run (one per comparable / language set)
    research_grok_cost_per_search_usd: float = 0.25  # pre-check estimate; actual cost from usage ticks
    research_search_days: int = 90  # x_search from_date window
    research_grok_max_tool_calls: int = 3  # x_search tool calls Grok may make per search
    research_excluded_handles: list[str] = [
        "SteamDB",
        "IsThereAnyDeal",
        "GGDealsCom",
        "Fanatical",
        "GreenManGaming",
        "humble",
        "DekuDeals",
        "CheapAssGamer",
        "wario64",
        "videogamedeals",
    ]  # headroom kept for the analysis calls in the budget pre-check
    daily_budget_usd: float = 2.0
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Local default; for Supabase use postgresql+psycopg://... (and add a driver dependency).
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'app.db'}"
    db_auto_migrate: bool = True  # run `alembic upgrade head` on startup
    upload_dir: Path = BACKEND_DIR / "data" / "uploads"
    max_screenshots: int = 5
    max_key_art: int = 2
    max_image_upload_bytes: int = 15 * 1024 * 1024
    max_image_dimension: int = 1568  # longest side after downscaling (saves vision tokens)
    max_image_pixels: int = 50_000_000  # decompression-bomb guard


@lru_cache
def get_settings() -> Settings:
    return Settings()
