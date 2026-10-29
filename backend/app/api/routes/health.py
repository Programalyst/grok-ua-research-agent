from fastapi import APIRouter, Depends

from app.api.deps import get_provider
from app.providers import LLMProvider
from app.schemas.dto import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(provider: LLMProvider = Depends(get_provider)) -> HealthOut:
    return HealthOut(status="ok", provider=provider.name)
