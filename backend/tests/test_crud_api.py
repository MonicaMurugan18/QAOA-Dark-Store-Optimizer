"""Store, product and demand API, including input validation."""


# ===================================================================== stores
def test_list_stores(client):
    r = client.get("/api/stores")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 6
    assert {"id", "name", "area", "opening_cost", "storage_capacity"} <= set(body[0])


def test_stores_filter_by_area(client):
    r = client.get("/api/stores", params={"area": "Venkata Nagar"})
    assert r.status_code == 200
    assert len(r.json()) == 3, "3 stores in Venkata Nagar per the project owner"


def test_store_get_one_and_404(client):
    assert client.get("/api/stores/1").json()["id"] == 1
    r = client.get("/api/stores/999999")
    assert r.status_code == 404
    assert "does not exist" in r.json()["detail"]


def test_store_create_update_delete(client):
    payload = {
        "name": "Test Hub",
        "area": "Test Area",
        "latitude": 11.94,
        "longitude": 79.81,
        "opening_cost": 5000,
        "storage_capacity": 1000,
    }
    r = client.post("/api/stores", json=payload)
    assert r.status_code == 201
    new_id = r.json()["id"]

    r = client.put(f"/api/stores/{new_id}", json={"opening_cost": 6100})
    assert r.status_code == 200
    assert r.json()["opening_cost"] == 6100

    assert client.delete(f"/api/stores/{new_id}").status_code == 204
    assert client.get(f"/api/stores/{new_id}").status_code == 404


def test_store_negative_opening_cost_rejected(client):
    r = client.post(
        "/api/stores",
        json={
            "name": "Bad",
            "area": "X",
            "latitude": 11.9,
            "longitude": 79.8,
            "opening_cost": -1,
            "storage_capacity": 100,
        },
    )
    assert r.status_code == 422
    assert "opening_cost" in str(r.json())


def test_store_negative_capacity_rejected(client):
    r = client.post(
        "/api/stores",
        json={
            "name": "Bad",
            "area": "X",
            "latitude": 11.9,
            "longitude": 79.8,
            "opening_cost": 100,
            "storage_capacity": -5,
        },
    )
    assert r.status_code == 422


def test_store_invalid_latitude_rejected(client):
    r = client.post(
        "/api/stores",
        json={
            "name": "Bad",
            "area": "X",
            "latitude": 120,
            "longitude": 79.8,
            "opening_cost": 100,
            "storage_capacity": 100,
        },
    )
    assert r.status_code == 422


# =================================================================== products
def test_list_products(client):
    r = client.get("/api/products")
    assert r.status_code == 200
    assert len(r.json()) >= 3


def test_product_create_update_delete(client):
    r = client.post(
        "/api/products",
        json={
            "name": "Test SKU",
            "category": "Test",
            "unit_volume": 0.4,
            "unit_cost": 30,
        },
    )
    assert r.status_code == 201
    pid = r.json()["id"]

    r = client.put(f"/api/products/{pid}", json={"unit_cost": 35})
    assert r.status_code == 200
    assert r.json()["unit_cost"] == 35

    assert client.delete(f"/api/products/{pid}").status_code == 204


def test_product_zero_unit_volume_rejected(client):
    """A zero-volume product would make the capacity constraint meaningless."""
    r = client.post(
        "/api/products",
        json={"name": "Massless", "category": "X", "unit_volume": 0, "unit_cost": 10},
    )
    assert r.status_code == 422


def test_product_negative_unit_cost_rejected(client):
    r = client.post(
        "/api/products",
        json={"name": "Bad", "category": "X", "unit_volume": 1, "unit_cost": -4},
    )
    assert r.status_code == 422


def test_product_unknown_id_404(client):
    assert client.get("/api/products/999999").status_code == 404


# ===================================================================== demand
def test_list_demand(client):
    r = client.get("/api/demand")
    assert r.status_code == 200
    assert len(r.json()) >= 9


def test_demand_filter_by_area(client):
    r = client.get("/api/demand", params={"area": "Lawspet"})
    assert r.status_code == 200
    assert all(row["area"] == "Lawspet" for row in r.json())


def test_demand_negative_quantity_rejected(client):
    r = client.post(
        "/api/demand",
        json={
            "area": "Lawspet",
            "product_id": 1,
            "demand_quantity": -10,
            "delivery_time_limit": 15,
        },
    )
    assert r.status_code == 422
    assert "demand_quantity" in str(r.json())


def test_demand_zero_delivery_limit_rejected(client):
    r = client.post(
        "/api/demand",
        json={
            "area": "Lawspet",
            "product_id": 1,
            "demand_quantity": 10,
            "delivery_time_limit": 0,
        },
    )
    assert r.status_code == 422


def test_demand_unknown_product_id_rejected(client):
    r = client.post(
        "/api/demand",
        json={
            "area": "Lawspet",
            "product_id": 999999,
            "demand_quantity": 10,
            "delivery_time_limit": 15,
        },
    )
    assert r.status_code == 422
    assert "999999" in str(r.json())


def test_demand_bulk_insert(client):
    r = client.post(
        "/api/demand/bulk",
        json={
            "items": [
                {
                    "area": "Bulk Area",
                    "product_id": 1,
                    "demand_quantity": 50,
                    "delivery_time_limit": 15,
                },
                {
                    "area": "Bulk Area",
                    "product_id": 2,
                    "demand_quantity": 60,
                    "delivery_time_limit": 15,
                },
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created"] + body["updated"] == 2


def test_demand_bulk_rejects_whole_batch_on_bad_row(client):
    """One invalid product id must not leave the table half written."""
    before = len(client.get("/api/demand", params={"area": "Atomic"}).json())
    r = client.post(
        "/api/demand/bulk",
        json={
            "items": [
                {
                    "area": "Atomic",
                    "product_id": 1,
                    "demand_quantity": 5,
                    "delivery_time_limit": 15,
                },
                {
                    "area": "Atomic",
                    "product_id": 424242,
                    "demand_quantity": 5,
                    "delivery_time_limit": 15,
                },
            ]
        },
    )
    assert r.status_code == 422
    after = len(client.get("/api/demand", params={"area": "Atomic"}).json())
    assert after == before, "a rejected batch must write nothing"
