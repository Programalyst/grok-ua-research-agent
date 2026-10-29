def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "provider": "fake"}


def test_create_and_list_games(client, game):
    assert game["hashtags"] == ["Starfall"] and game["handles"] == ["starfall"]
    r = client.get("/api/v1/games")
    assert [g["id"] for g in r.json()] == [game["id"]]
    r = client.patch(f"/api/v1/games/{game['id']}", json={"languages": ["ja"]})
    assert r.json()["languages"] == ["ja"]


def test_validation_and_404(client):
    assert client.post("/api/v1/games", json={"name": ""}).status_code == 422
    assert client.post("/api/v1/games", json={"name": "x", "languages": ["fr"]}).status_code == 422
    assert client.get("/api/v1/games/nope").status_code == 404
    assert client.post("/api/v1/games/nope/scans").status_code == 404


def test_scan_posts_insights(client, game):
    gid = game["id"]
    r = client.post(f"/api/v1/games/{gid}/scans", json={"max_posts": 20})
    assert r.status_code == 201
    scan = r.json()
    assert scan["status"] == "completed" and scan["post_count"] == 20
    assert client.get(f"/api/v1/scans/{scan['id']}").json()["id"] == scan["id"]

    posts = client.get(f"/api/v1/games/{gid}/posts").json()
    assert len(posts) == 20
    assert {p["language"] for p in posts} == {"en", "ja", "ko", "zh"}
    bugs = client.get(f"/api/v1/games/{gid}/posts", params={"category": "bug"}).json()
    assert bugs and all(p["category"] == "bug" for p in bugs)

    ins = client.get(f"/api/v1/games/{gid}/insights").json()
    assert ins["total_posts"] == 20
    assert sum(ins["sentiment_totals"].values()) == 20
    assert ins["top_issues"] and ins["spikes"]
    assert ins["spikes"][0]["reason"] == "influencer"


def test_delete_game(client, game):
    assert client.delete(f"/api/v1/games/{game['id']}").status_code == 204
    assert client.get("/api/v1/games").json() == []
