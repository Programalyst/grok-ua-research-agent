import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.deps import get_collector, get_provider, get_repository, get_x_client
from app.config import Settings, get_settings
from app.db import make_engine
from app.main import app
from app.providers import FakeProvider
from app.repositories import InMemoryRepository, SqlRepository
from app.x import FakeXClient, XApiCollector


def make_image(fmt: str = "PNG", size: tuple[int, int] = (32, 24), color=(200, 120, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture(params=["sql", "memory"])
def repo_kind(request) -> str:
    return request.param


@pytest.fixture
def settings(tmp_path, repo_kind) -> Settings:
    # Temp SQLite file per test; migrations run through the app lifespan (same path as production).
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        db_auto_migrate=repo_kind == "sql",
        upload_dir=tmp_path / "uploads",
        max_screenshots=2,
        max_key_art=1,
        max_image_upload_bytes=200_000,
        max_image_dimension=64,
    )


@pytest.fixture
def client(settings, repo_kind):
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    fake_x = FakeXClient()
    app.dependency_overrides[get_x_client] = lambda: fake_x
    app.dependency_overrides[get_collector] = lambda: XApiCollector(fake_x)
    with TestClient(app) as c:  # lifespan migrates the temp DB first
        repo = SqlRepository(make_engine(settings.database_url)) if repo_kind == "sql" else InMemoryRepository()
        app.dependency_overrides[get_repository] = lambda: repo
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def repo(client):
    return app.dependency_overrides[get_repository]()


@pytest.fixture
def game(client):
    r = client.post(
        "/api/v1/games",
        json={"name": "Starfall", "hashtags": ["#Starfall"], "handles": ["@starfall"], "keywords": ["starfall launch"]},
    )
    assert r.status_code == 201
    return r.json()
