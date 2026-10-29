from tests.conftest import make_image

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32

BRIEF = {
    "name": "Moonforge",
    "pitch": "A cozy roguelike about rebuilding a lunar village",
    "description": "Explore, craft, and defend.",
    "genres": ["Roguelike", "Cozy", "roguelike"],
    "platforms": ["pc", "ios"],
    "regions": ["NA", "JP"],
    "languages": ["en", "ja"],
    "differentiators": "Co-op village building between runs. Hand-painted art.",
    "comparable_games": ["Hades", "Stardew Valley"],
}


def _create(client):
    r = client.post("/api/v1/games", json=BRIEF)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_brief(client):
    g = _create(client)
    assert g["genres"] == ["Roguelike", "Cozy"]  # deduped case-insensitively
    assert g["platforms"] == ["pc", "ios"] and g["images"] == [] and g["has_profile"] is False


def test_brief_validation(client):
    assert client.post("/api/v1/games", json={**BRIEF, "platforms": ["switch"]}).status_code == 422
    assert client.post("/api/v1/games", json={**BRIEF, "comparable_games": list("abcdef")}).status_code == 422
    assert client.post("/api/v1/games", json={**BRIEF, "pitch": "x" * 281}).status_code == 422


def test_image_upload_kinds_webp_and_limits(client):
    gid = _create(client)["id"]
    base = f"/api/v1/games/{gid}/images"
    r = client.post(base, files={"file": ("shot.webp", make_image("WEBP", (200, 100)), "image/webp")})
    assert r.status_code == 201, r.text
    shot = r.json()
    # WebP converted to PNG, downscaled to max_image_dimension (64) keeping aspect ratio
    assert shot["kind"] == "screenshot" and shot["content_type"] == "image/png"
    assert (shot["width"], shot["height"]) == (64, 32) and shot["url"] == f"{base}/{shot['id']}"
    img = client.get(shot["url"])
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG") and img.headers["content-type"] == "image/png"

    art = client.post(base, data={"kind": "key_art"}, files={"file": ("art.jpg", make_image("JPEG"), "image/jpeg")})
    assert art.status_code == 201 and art.json()["kind"] == "key_art" and art.json()["content_type"] == "image/jpeg"
    # key art limit (1) is independent of the screenshot limit (2)
    assert (
        client.post(base, data={"kind": "key_art"}, files={"file": ("a2.png", make_image(), "image/png")}).status_code
        == 409
    )
    assert client.post(base, files={"file": ("s2.png", make_image(), "image/png")}).status_code == 201
    assert client.post(base, files={"file": ("s3.png", make_image(), "image/png")}).status_code == 409

    # content is decoded, not trusted: fake PNG header, GIF, oversized, bad kind
    assert client.post(base, data={"kind": "key_art"}, files={"file": ("x.png", PNG, "image/png")}).status_code in (
        409,
        415,
    )
    bad = client.post(f"/api/v1/games/{_create(client)['id']}/images", files={"file": ("x.png", PNG, "image/png")})
    assert bad.status_code == 415
    gif = make_image("GIF")
    assert (
        client.post(
            f"/api/v1/games/{_create(client)['id']}/images", files={"file": ("g.gif", gif, "image/gif")}
        ).status_code
        == 415
    )
    big = b"0" * 200_001
    assert (
        client.post(
            f"/api/v1/games/{_create(client)['id']}/images", files={"file": ("b.png", big, "image/png")}
        ).status_code
        == 413
    )
    assert (
        client.post(base, data={"kind": "logo"}, files={"file": ("l.png", make_image(), "image/png")}).status_code
        == 422
    )

    assert [i["kind"] for i in client.get(base, params={"kind": "key_art"}).json()] == ["key_art"]
    assert client.delete(f"{base}/{shot['id']}").status_code == 204
    assert client.get(shot["url"]).status_code == 404
    assert len(client.get(f"/api/v1/games/{gid}").json()["images"]) == 2


def test_seed_keywords_and_long_description(client):
    long = "x" * 5000
    r = client.post(
        "/api/v1/games",
        json={
            **BRIEF,
            "description": long,
            "differentiators": long,
            "seed_keywords": {"ZH": ["战棋", "战棋", " 末日 "], "ja": []},
        },
    )
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["seed_keywords"] == {"zh": ["战棋", "末日"]} and len(g["description"]) == 5000
    assert client.post("/api/v1/games", json={**BRIEF, "description": long + "x"}).status_code == 422
    upd = client.patch(f"/api/v1/games/{g['id']}", json={"seed_keywords": {"ja": ["シミュレーションRPG"]}})
    assert upd.json()["seed_keywords"] == {"ja": ["シミュレーションRPG"]}
    prof = client.post(f"/api/v1/games/{g['id']}/profile/generate").json()
    assert prof["keywords_by_language"]["ja"][0] == "シミュレーションRPG"  # fake provider puts seeds first


def test_generate_and_edit_profile(client):
    gid = _create(client)["id"]
    assert client.get(f"/api/v1/games/{gid}/profile").status_code == 404
    r = client.post(f"/api/v1/games/{gid}/profile/generate")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["generated_by"] == "fake" and set(p["keywords_by_language"]) == {"en", "ja"}
    names = [c["name"] for c in p["suggested_comparables"]]
    assert names and "Hades" not in names and all(c["status"] == "suggested" for c in p["suggested_comparables"])
    # deterministic
    assert client.post(f"/api/v1/games/{gid}/profile/generate").json()["themes"] == p["themes"]

    edited = {
        **p,
        "themes": ["co-op building"],
        "target_audience": "Cozy co-op fans",
        "suggested_comparables": [{**p["suggested_comparables"][0], "status": "accepted"}],
    }
    r = client.put(f"/api/v1/games/{gid}/profile", json=edited)
    assert r.status_code == 200 and r.json()["edited"] is True
    got = client.get(f"/api/v1/games/{gid}/profile").json()
    assert got["themes"] == ["co-op building"] and got["suggested_comparables"][0]["status"] == "accepted"
    assert client.get(f"/api/v1/games/{gid}").json()["has_profile"] is True
