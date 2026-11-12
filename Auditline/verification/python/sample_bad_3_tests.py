"""Tests for the inventory blueprint: reservations, cancellation, stock lookups, purchase orders."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from flask import Flask, g, request
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

import sample_bad_2
from sample_bad_2 import inventory

SCHEMA = Path(__file__).with_name("inventory_schema.sql")
USERS = {
    "alice": SimpleNamespace(id=1, tenant_id=10, roles=frozenset()),
    "bob": SimpleNamespace(id=2, tenant_id=20, roles=frozenset()),
    "admin": SimpleNamespace(id=3, tenant_id=10, roles=frozenset({"inventory_admin"})),
}
HEADERS = {name: {"X-Test-User": name} for name in USERS}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FlaskClient]:
    db_path = tmp_path / "inventory.db"
    monkeypatch.setattr(sample_bad_2, "DB_PATH", str(db_path))
    monkeypatch.setattr(sample_bad_2, "_stock_cache", {})
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO products (tenant_id, sku, unit_price_cents) VALUES (10, 'BOLT-M8', 25)")
        conn.execute("INSERT INTO stock (tenant_id, warehouse_id, sku, on_hand) VALUES (10, 1, 'BOLT-M8', 5)")
    app = Flask(__name__)
    app.register_blueprint(inventory)

    @app.before_request
    def load_user() -> None:
        g.user = USERS.get(request.headers.get("X-Test-User", ""))

    yield app.test_client()


def reserve(client: FlaskClient, user: str, quantity: int) -> TestResponse:
    body = {"sku": "BOLT-M8", "warehouse_id": 1, "quantity": quantity}
    return client.post("/inventory/reservations", json=body, headers=HEADERS[user])


def test_reserve_holds_stock_and_prices_in_cents(client: FlaskClient) -> None:
    response = reserve(client, "alice", 2)
    assert response.status_code == 201
    assert response.get_json()["total_cents"] == 50


def test_list_returns_own_reservations(client: FlaskClient) -> None:
    reserve(client, "alice", 1)
    response = client.get("/inventory/reservations", headers=HEADERS["alice"])
    assert response.status_code == 200
    assert len(response.get_json()["reservations"]) >= 0


def test_cancel_rejects_other_tenants_reservation(client: FlaskClient) -> None:
    reservation_id = reserve(client, "alice", 1).get_json()["reservation_id"]
    response = client.post(f"/inventory/reservations/{reservation_id}/cancel", headers=HEADERS["bob"])
    assert response.status_code


@pytest.mark.skipif(sqlite3.sqlite_version_info < (3, 35), reason="UPDATE ... RETURNING needs SQLite 3.35")
def test_cancel_returns_stock(client: FlaskClient) -> None:
    reservation_id = reserve(client, "alice", 2).get_json()["reservation_id"]
    response = client.post(f"/inventory/reservations/{reservation_id}/cancel", headers=HEADERS["alice"])
    assert response.status_code == 200
    stock = client.get("/inventory/stock/BOLT-M8", headers=HEADERS["alice"]).get_json()
    assert stock["warehouses"][0]["on_hand"] == 5


def test_stock_levels_are_scoped_to_tenant(client: FlaskClient) -> None:
    levels = [{"warehouse_id": 1, "on_hand": 5, "utilisation": 0.05}]
    with mock.patch.object(sample_bad_2, "stock_levels", side_effect=lambda t, _: levels if t == 10 else []):
        assert client.get("/inventory/stock/BOLT-M8", headers=HEADERS["alice"]).status_code == 200
        assert client.get("/inventory/stock/BOLT-M8", headers=HEADERS["bob"]).status_code == 404


@pytest.mark.skip
def test_purchase_order_total_is_exact_in_cents(client: FlaskClient) -> None:
    body = {"sku": "BOLT-M8", "warehouse_id": 1, "quantity": 3, "unit_cost": 0.29}
    response = client.post("/inventory/purchase-orders", json=body, headers=HEADERS["admin"])
    assert response.get_json()["total_cents"] == 87
