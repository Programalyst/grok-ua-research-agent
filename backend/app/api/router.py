from fastapi import APIRouter

from app.api.routes import games, health, images, insights, posts, profile, research, scans

api_router = APIRouter(prefix="/api/v1")
for r in (
    health.router,
    games.router,
    images.router,
    profile.router,
    scans.router,
    posts.router,
    insights.router,
    research.router,
):
    api_router.include_router(r)
