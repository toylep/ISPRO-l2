import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_get_washers_returns_list():
    response = client.get("/washers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 10


def test_get_washers_item_schema():
    response = client.get("/washers")
    item = response.json()[0]
    assert "id" in item
    assert "state" in item
    assert item["state"] in ("available", "unavailable", "broken")


def test_book_washer_success():
    response = client.post("/washers/book", json={"washer_id": 1, "hours": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["washer_id"] == 1
    assert data["hours"] == 2
    assert "id" in data


def test_book_washer_missing_fields():
    response = client.post("/washers/book", json={"washer_id": 1})
    assert response.status_code == 422


def test_book_washer_invalid_body():
    response = client.post("/washers/book", json={})
    assert response.status_code == 422


def test_my_books_returns_list():
    response = client.get("/washers/my-books")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 5


def test_my_books_item_schema():
    response = client.get("/washers/my-books")
    item = response.json()[0]
    assert "id" in item
    assert "washer_id" in item
    assert "hours" in item


@pytest.mark.parametrize("state", ["available", "unavailable", "broken"])
def test_change_washer_state(state):
    response = client.put("/washers/3", json={"state": state})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 3
    assert data["state"] == state


def test_change_washer_state_invalid():
    response = client.put("/washers/1", json={"state": "flying"})
    assert response.status_code == 422


def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
