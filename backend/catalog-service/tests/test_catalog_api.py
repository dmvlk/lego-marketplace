import asyncio
import base64
import io
import os
import uuid

import asyncpg
import httpx
import pytest
from PIL import Image


BASE_URL = "http://gateway:8000/api/v1"


async def cleanup_test_records(suffix: str, listing_id: str | None) -> None:
    database_url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    catalog_db = await asyncpg.connect(database_url)
    try:
        if listing_id:
            await catalog_db.execute("DELETE FROM listings WHERE id = $1", uuid.UUID(listing_id))
    finally:
        await catalog_db.close()

    auth_db = await asyncpg.connect(database_url.replace("/catalog_db", "/auth_db"))
    try:
        await auth_db.execute(
            "DELETE FROM users WHERE email = ANY($1::text[])",
            [f"seller_{suffix}@example.com", f"buyer_{suffix}@example.com"],
        )
    finally:
        await auth_db.close()


@pytest.fixture
def cleanup_records(request):
    suffix = uuid.uuid4().hex[:10]
    state = {"listing_id": None}
    request.addfinalizer(lambda: asyncio.run(cleanup_test_records(suffix, state["listing_id"])))
    return suffix, state


def register_user(client: httpx.Client, name: str, suffix: str) -> dict:
    response = client.post(
        f"{BASE_URL}/auth/register",
        json={
            "email": f"{name}_{suffix}@example.com",
            "password": "StrongPass123!",
            "display_name": name,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_catalog_listing_flow(cleanup_records) -> None:
    suffix, cleanup_state = cleanup_records
    with httpx.Client(timeout=15.0) as client:
        categories = client.get(f"{BASE_URL}/catalog/categories")
        themes = client.get(f"{BASE_URL}/catalog/themes")
        assert categories.status_code == 200
        assert len(categories.json()) == 3
        assert themes.status_code == 200
        assert len(themes.json()) >= 7

        seller = register_user(client, "seller", suffix)
        buyer = register_user(client, "buyer", suffix)
        seller_headers = {"Authorization": f"Bearer {seller['access_token']}"}
        buyer_headers = {"Authorization": f"Bearer {buyer['access_token']}"}

        created = client.post(
            f"{BASE_URL}/catalog/listings",
            headers=seller_headers,
            json={
                "category_id": categories.json()[0]["id"],
                "title": f"LEGO test {suffix}",
                "description": "Полный набор в хорошем состоянии.",
                "price": "1250.50",
                "condition": "USED",
            },
        )
        assert created.status_code == 201
        listing_id = created.json()["id"]
        cleanup_state["listing_id"] = listing_id

        malformed_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/VKkAAAAASUVORK5CYII="
        )
        invalid_upload = client.post(
            f"{BASE_URL}/catalog/listings/{listing_id}/images",
            headers=seller_headers,
            files={"file": ("broken.png", malformed_png, "image/png")},
        )
        assert invalid_upload.status_code == 415

        seller_listings = client.get(
            f"{BASE_URL}/catalog/my-listings",
            headers=seller_headers,
        )
        buyer_listings = client.get(
            f"{BASE_URL}/catalog/my-listings",
            headers=buyer_headers,
        )
        assert seller_listings.status_code == 200
        assert seller_listings.json()["total"] == 1
        assert seller_listings.json()["items"][0]["id"] == listing_id
        assert buyer_listings.status_code == 200
        assert buyer_listings.json()["total"] == 0

        image_buffer = io.BytesIO()
        Image.new("RGB", (4, 4), "red").save(image_buffer, format="PNG")
        uploaded = client.post(
            f"{BASE_URL}/catalog/listings/{listing_id}/images",
            headers=seller_headers,
            files={"file": ("photo.png", image_buffer.getvalue(), "image/png")},
        )
        assert uploaded.status_code == 201
        image_reference = uploaded.json()["image_reference"]
        image_response = client.get(f"http://gateway:8000{image_reference}")
        assert image_response.status_code == 200
        assert image_response.headers["content-type"] == "image/png"

        detail = client.get(f"{BASE_URL}/catalog/listings/{listing_id}")
        assert detail.status_code == 200
        assert detail.json()["image_references"] == [image_reference]

        for _ in range(2):
            favorite = client.post(
                f"{BASE_URL}/catalog/listings/{listing_id}/favorites",
                headers=buyer_headers,
            )
            assert favorite.status_code == 201
        favorites = client.get(f"{BASE_URL}/catalog/favorites", headers=buyer_headers)
        assert favorites.status_code == 200
        assert favorites.json()["total"] == 1
        assert favorites.json()["items"][0]["id"] == listing_id

        search = client.get(
            f"{BASE_URL}/catalog/listings",
            params={"q": suffix, "sort": "price_asc"},
        )
        assert search.status_code == 200
        assert search.json()["total"] == 1

        invalid_range = client.get(
            f"{BASE_URL}/catalog/listings",
            params={"min_price": "2000", "max_price": "1000"},
        )
        assert invalid_range.status_code == 422

        invalid_image = client.post(
            f"{BASE_URL}/catalog/listings/{listing_id}/images",
            headers=seller_headers,
            files={"file": ("notes.txt", b"not an image", "text/plain")},
        )
        assert invalid_image.status_code == 415

        forbidden_update = client.patch(
            f"{BASE_URL}/catalog/listings/{listing_id}",
            headers=buyer_headers,
            json={"title": "Чужое объявление"},
        )
        assert forbidden_update.status_code == 403
        owner_update = client.patch(
            f"{BASE_URL}/catalog/listings/{listing_id}",
            headers=seller_headers,
            json={"price": "1300.00"},
        )
        assert owner_update.status_code == 200
        assert owner_update.json()["price"] == "1300.00"

        forbidden_image_delete = client.delete(
            f"{BASE_URL}/catalog/listings/{listing_id}/images/{uploaded.json()['image_id']}",
            headers=buyer_headers,
        )
        assert forbidden_image_delete.status_code == 403

        removed = client.delete(
            f"{BASE_URL}/catalog/listings/{listing_id}/images/{uploaded.json()['image_id']}",
            headers=seller_headers,
        )
        assert removed.status_code == 204

        listing = client.get(f"{BASE_URL}/catalog/listings/{listing_id}")
        assert listing.json()["image_references"] == []

        removed_favorite = client.delete(
            f"{BASE_URL}/catalog/listings/{listing_id}/favorites",
            headers=buyer_headers,
        )
        assert removed_favorite.status_code == 204
        assert client.get(
            f"{BASE_URL}/catalog/favorites",
            headers=buyer_headers,
        ).json()["total"] == 0

        archived = client.delete(
            f"{BASE_URL}/catalog/listings/{listing_id}",
            headers=seller_headers,
        )
        assert archived.status_code == 204
        assert client.get(f"{BASE_URL}/catalog/listings/{listing_id}").status_code == 404
