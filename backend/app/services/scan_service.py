from datetime import UTC, datetime

from app.models import Game, Post, Scan, ScanStatus
from app.providers import LLMProvider
from app.repositories import Repository


class ScanService:
    def __init__(self, repo: Repository, provider: LLMProvider) -> None:
        self._repo = repo
        self._provider = provider

    async def run_scan(self, game: Game, max_posts: int) -> Scan:
        scan = self._repo.add_scan(Scan(game_id=game.id, provider=self._provider.name, status=ScanStatus.RUNNING))
        try:
            raw = await self._provider.search_and_classify(game, max_posts)
            posts = [
                Post(
                    game_id=game.id,
                    scan_id=scan.id,
                    text=r.text,
                    author=r.author,
                    language=r.language,
                    sentiment=r.sentiment,
                    category=r.category,
                    url=r.url,
                    posted_at=r.posted_at,
                    likes=r.likes,
                    reposts=r.reposts,
                    replies=r.replies,
                    author_followers=r.author_followers,
                )
                for r in raw
            ]
            self._repo.add_posts(posts)
            scan.post_count = len(posts)
            scan.status = ScanStatus.COMPLETED
        except Exception as exc:  # noqa: BLE001 - surface provider failures on the scan
            scan.status = ScanStatus.FAILED
            scan.error = str(exc)
        scan.finished_at = datetime.now(UTC)
        return self._repo.update_scan(scan)
