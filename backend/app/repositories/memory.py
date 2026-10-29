from datetime import datetime
from threading import Lock

from app.models import Game, Post, ResearchPost, ResearchRun, Scan, UsageRecord, XAuthor


class InMemoryRepository:
    def __init__(self) -> None:
        self._games: dict[str, Game] = {}
        self._scans: dict[str, Scan] = {}
        self._posts: dict[str, Post] = {}
        self._usage: list[UsageRecord] = []
        self._runs: dict[str, ResearchRun] = {}
        self._rposts: list[ResearchPost] = []
        self._authors: dict[str, XAuthor] = {}
        self._lock = Lock()

    def add_game(self, game: Game) -> Game:
        with self._lock:
            self._games[game.id] = game
        return game

    def get_game(self, game_id: str) -> Game | None:
        return self._games.get(game_id)

    def list_games(self) -> list[Game]:
        return sorted(self._games.values(), key=lambda g: g.created_at)

    def update_game(self, game: Game) -> Game:
        return self.add_game(game)

    def delete_game(self, game_id: str) -> bool:
        with self._lock:
            existed = self._games.pop(game_id, None) is not None
            self._scans = {k: s for k, s in self._scans.items() if s.game_id != game_id}
            self._posts = {k: p for k, p in self._posts.items() if p.game_id != game_id}
            self._runs = {k: r for k, r in self._runs.items() if r.game_id != game_id}
            self._rposts = [p for p in self._rposts if p.game_id != game_id]
        return existed

    def add_scan(self, scan: Scan) -> Scan:
        with self._lock:
            self._scans[scan.id] = scan
        return scan

    def update_scan(self, scan: Scan) -> Scan:
        return self.add_scan(scan)

    def get_scan(self, scan_id: str) -> Scan | None:
        return self._scans.get(scan_id)

    def list_scans(self, game_id: str) -> list[Scan]:
        return sorted(
            (s for s in self._scans.values() if s.game_id == game_id), key=lambda s: s.started_at, reverse=True
        )

    def add_posts(self, posts: list[Post]) -> None:
        with self._lock:
            for p in posts:
                self._posts[p.id] = p

    def list_posts(self, game_id: str) -> list[Post]:
        return sorted(
            (p for p in self._posts.values() if p.game_id == game_id), key=lambda p: p.posted_at, reverse=True
        )

    def add_usage(self, record: UsageRecord) -> None:
        with self._lock:
            self._usage.append(record)

    def usage_cost_since(self, since: datetime) -> float:
        return sum(u.cost_usd for u in self._usage if u.created_at >= since)

    # research
    def add_research_run(self, run: ResearchRun) -> ResearchRun:
        with self._lock:
            self._runs[run.id] = run
        return run

    def update_research_run(self, run: ResearchRun) -> ResearchRun:
        return self.add_research_run(run)

    def get_research_run(self, run_id: str) -> ResearchRun | None:
        return self._runs.get(run_id)

    def list_research_runs(self, game_id: str) -> list[ResearchRun]:
        return sorted(
            (r for r in self._runs.values() if r.game_id == game_id), key=lambda r: r.started_at, reverse=True
        )

    def add_research_posts(self, items: list[ResearchPost]) -> None:
        with self._lock:
            self._rposts.extend(items)

    def list_research_posts(self, run_id: str) -> list[ResearchPost]:
        return [p for p in self._rposts if p.run_id == run_id]

    def upsert_authors(self, authors: list[XAuthor]) -> None:
        with self._lock:
            self._authors.update({a.id: a for a in authors})

    def get_authors(self, author_ids: list[str]) -> dict[str, XAuthor]:
        return {i: self._authors[i] for i in author_ids if i in self._authors}
