import io
import json

import pytest
from PIL import Image


@pytest.fixture(autouse=True)
def photos_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PHOTOS_DIR", str(tmp_path))
    return tmp_path


def png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def red_and_blue() -> Image.Image:
    """40x20: the left half pure red, the right half pure blue."""
    image = Image.new("RGB", (40, 20), (255, 0, 0))
    image.paste((0, 0, 255), (20, 0, 40, 20))
    return image


def upload(client, data: bytes, content_type: str = "image/png"):
    return client.post("/photos", content=data, headers={"Content-Type": content_type})


def test_an_uploaded_photo_is_stored_and_read_back_unchanged(client):
    original = png(red_and_blue())

    created = upload(client, original)

    assert created.status_code == 201
    photo = created.json()
    assert photo["rank"] is None and photo["reason"] is None
    assert client.get("/photos").json() == [photo]
    image = client.get(f"/photos/{photo['id']}/image")
    assert image.headers["content-type"] == "image/png"
    assert image.content == original


def test_an_upload_that_is_not_a_small_jpeg_or_png_is_refused(client, monkeypatch):
    assert upload(client, b"GIF89a", "image/gif").status_code == 415
    assert upload(client, b"not an image").status_code == 422
    assert upload(client, png(red_and_blue()), "image/jpeg").status_code == 422  # the type must match the file
    monkeypatch.setattr("app.photos.MAX_BYTES", 50)
    assert upload(client, png(red_and_blue())).status_code == 413
    assert client.get("/photos").json() == []


def test_a_photo_is_only_visible_to_its_owner(client_for):
    alice, bob = client_for("alice@example.com"), client_for("bob@example.com")
    photo = upload(alice, png(red_and_blue())).json()

    assert bob.get("/photos").json() == []
    assert bob.get(f"/photos/{photo['id']}/image").status_code == 404


def test_ranking_shows_claude_the_photos_and_returns_them_best_first_with_a_reason_each(client, llm):
    first = upload(client, png(red_and_blue())).json()["id"]
    second = upload(client, png(Image.new("RGB", (10, 10), "green"))).json()["id"]
    llm.reply = json.dumps(
        [{"id": second, "reason": "Clear face, good light."}, {"id": first, "reason": "Too dark."}]
    )

    ranked = client.post("/photos/rank")

    assert ranked.status_code == 200
    assert [(photo["id"], photo["rank"], photo["reason"]) for photo in ranked.json()] == [
        (second, 1, "Clear face, good light."),
        (first, 2, "Too dark."),
    ]
    assert client.get("/photos").json() == ranked.json()
    # Claude saw both photos, in id order, as JPEGs of the uploaded pixels (so within a few levels of them).
    seen = [Image.open(io.BytesIO(data)).convert("RGB").getpixel((0, 0)) for _, data in llm.images[-1]]
    for pixel, uploaded in zip(seen, [(255, 0, 0), (0, 128, 0)], strict=True):
        assert all(abs(got - want) <= 4 for got, want in zip(pixel, uploaded, strict=False))
    assert str(first) in llm.prompts[-1] and str(second) in llm.prompts[-1]


def test_a_ranking_that_does_not_cover_exactly_the_users_photos_is_reported_not_stored(client, llm):
    photo = upload(client, png(red_and_blue())).json()
    for reply in ["not json", "[]", json.dumps([{"id": photo["id"] + 1, "reason": "?"}])]:
        llm.reply = reply
        assert client.post("/photos/rank").status_code == 502
    assert client.get("/photos").json() == [photo]


def offer(client, llm, edit: dict) -> int:
    """Upload the red and blue photo and have the ranking offer `edit` for it. Returns the photo's id."""
    photo_id = upload(client, png(red_and_blue())).json()["id"]
    llm.reply = json.dumps([{"id": photo_id, "reason": "Crop out the blue.", "edit": edit}])
    assert client.post("/photos/rank").json()[0]["suggested_edit"] == edit
    return photo_id


LEFT_HALF = {"crop": [0, 0, 0.5, 1], "exposure": 1, "colour": 1}


def test_an_edit_preview_is_made_only_from_the_original_pixels(client, llm):
    photo_id = offer(client, llm, LEFT_HALF)
    calls = len(llm.prompts)

    preview = client.get(f"/photos/{photo_id}/preview")

    assert preview.status_code == 200
    image = Image.open(io.BytesIO(preview.content))
    # Cropped to the left half: every pixel is the original's red, none is new.
    assert image.size == (20, 20)
    assert image.convert("RGB").getcolors() == [(400, (255, 0, 0))]
    assert len(llm.prompts) == calls  # no model was asked for the preview
    # The preview changed nothing: the photo is still the upload.
    assert client.get(f"/photos/{photo_id}/image").content == png(red_and_blue())


def test_exposure_and_colour_change_the_original_pixels_by_arithmetic(client, llm):
    photo_id = offer(client, llm, {"crop": None, "exposure": 0.5, "colour": 0.5})

    image = Image.open(io.BytesIO(client.get(f"/photos/{photo_id}/preview").content)).convert("RGB")

    # Exposure 0.5 halves each channel: red (255, 0, 0) becomes (128, 0, 0), whose grey is 38. Colour 0.5 is
    # then halfway between the pixel and its grey: (83, 19, 19). The same sum for blue gives (7, 7, 71).
    assert image.size == (40, 20)
    for at, want in [((0, 0), (83, 19, 19)), ((39, 0), (7, 7, 71))]:
        assert all(abs(got - expected) <= 1 for got, expected in zip(image.getpixel(at), want, strict=False))


def test_an_accepted_edit_is_applied_to_the_photo_and_the_offer_is_gone(client, llm):
    photo_id = offer(client, llm, LEFT_HALF)

    accepted = client.put(f"/photos/{photo_id}/edit", json={"accept": True})

    assert accepted.status_code == 200
    assert accepted.json()["edit"] == LEFT_HALF and accepted.json()["suggested_edit"] is None
    assert Image.open(io.BytesIO(client.get(f"/photos/{photo_id}/image").content)).size == (20, 20)
    assert client.get(f"/photos/{photo_id}/preview").status_code == 404
    (entry,) = client.get("/audit-log").json()
    assert (entry["type"], entry["app"], entry["target"]) == ("profile_change", "all", f"photo:{photo_id}")
    assert entry["trigger"] == "copilot: user accepted a photo edit"


def test_a_rejected_edit_leaves_the_photo_as_uploaded(client, llm):
    photo_id = offer(client, llm, LEFT_HALF)

    rejected = client.put(f"/photos/{photo_id}/edit", json={"accept": False})

    assert client.get("/audit-log").json() == []
    assert rejected.json()["edit"] is None and rejected.json()["suggested_edit"] is None
    assert client.get(f"/photos/{photo_id}/image").content == png(red_and_blue())


def test_an_edit_that_is_not_light_is_refused_with_the_ranking(client, llm):
    photo_id = upload(client, png(red_and_blue())).json()["id"]
    for edit in [{"exposure": 3}, {"colour": -1}, {"crop": [0.5, 0, 0.2, 1]}, {"crop": [0, 0, 2, 1]}]:
        llm.reply = json.dumps([{"id": photo_id, "reason": "?", "edit": edit}])
        assert client.post("/photos/rank").status_code == 502


def test_ranking_needs_at_least_one_photo(client, llm):
    assert client.post("/photos/rank").status_code == 409
    assert llm.prompts == []


def test_a_deleted_photo_is_gone_from_the_users_photos(client, client_for, photos_dir):
    kept = upload(client, png(red_and_blue())).json()
    deleted = upload(client, png(Image.new("RGB", (10, 10), "green"))).json()["id"]
    other = client_for("bob@example.com")

    assert other.delete(f"/photos/{deleted}").status_code == 404  # only the owner deletes

    assert client.delete(f"/photos/{deleted}").status_code == 204
    assert client.get("/photos").json() == [kept]
    assert client.get(f"/photos/{deleted}/image").status_code == 404
    assert client.delete(f"/photos/{deleted}").status_code == 404
    assert not any(path.name == str(deleted) for path in photos_dir.rglob("*"))  # the file is gone too


def test_the_order_the_user_sets_is_the_order_returned(client, llm):
    first, second, third = (upload(client, png(red_and_blue())).json()["id"] for _ in range(3))
    llm.reply = json.dumps([{"id": id, "reason": f"Reason {id}."} for id in [first, second, third]])
    client.post("/photos/rank")

    ordered = client.put("/photos/order", json={"ids": [third, first, second]})

    assert ordered.status_code == 200
    assert [(photo["id"], photo["rank"], photo["reason"]) for photo in ordered.json()] == [
        (third, 1, f"Reason {third}."),
        (first, 2, f"Reason {first}."),
        (second, 3, f"Reason {second}."),
    ]
    assert client.get("/photos").json() == ordered.json()
    added = upload(client, png(red_and_blue())).json()["id"]
    assert [photo["id"] for photo in client.get("/photos").json()] == [third, first, second, added]


def test_an_order_that_does_not_name_exactly_the_users_photos_is_refused(client, client_for):
    mine = [upload(client, png(red_and_blue())).json()["id"] for _ in range(2)]
    theirs = upload(client_for("bob@example.com"), png(red_and_blue())).json()["id"]
    before = client.get("/photos").json()

    for ids in [mine[:1], [*mine, mine[0]], [mine[1], theirs], [*mine, theirs]]:
        assert client.put("/photos/order", json={"ids": ids}).status_code == 422
    assert client.get("/photos").json() == before
