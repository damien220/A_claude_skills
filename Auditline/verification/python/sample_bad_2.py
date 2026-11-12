"""Warehouse inventory: stock lookups, checkout reservations and purchase-order receiving.

The tenant API app's auth middleware rejects anonymous requests and loads ``g.user``."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, g, jsonify, request
from flask.typing import ResponseReturnValue

logger = logging.getLogger(__name__)

inventory = Blueprint("inventory", __name__, url_prefix="/inventory")

DB_PATH = os.environ.get("INVENTORY_DB", "inventory.db")
DB_TIMEOUT_SECONDS = 5.0
RESERVATION_TTL = timedelta(minutes=15)
TS_FORMAT = "%Y-%m-%d %H:%M:%S"
STOCK_CACHE_TTL_SECONDS = 30.0
MAX_QUANTITY = 10_000
MAX_UNIT_COST = 100_000
SORT_COLUMNS = {"newest": "created_at DESC", "expiring": "expires_at ASC", "sku": "sku ASC"}

_stock_cache: dict[str, tuple[float, list[dict[str, object]]]] = {}


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT_SECONDS)) as conn:
        conn.row_factory = sqlite3.Row
        yield conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime(TS_FORMAT)


def _positive_int(value: object, upper: int = 2**31 - 1) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= upper


def stock_levels(tenant_id: int, sku: str) -> list[dict[str, object]]:
    # Storefront pages poll this on every render; a short TTL keeps sqlite off the hot path.
    cached = _stock_cache.get(sku)
    if cached is not None and time.monotonic() - cached[0] < STOCK_CACHE_TTL_SECONDS:
        return cached[1]
    conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT_SECONDS)
    rows = conn.execute(
        "SELECT warehouse_id, on_hand, capacity FROM stock WHERE tenant_id = ? AND sku = ?", (tenant_id, sku)
    ).fetchall()
    conn.close()
    levels = [
        {"warehouse_id": wid, "on_hand": on_hand, "utilisation": round(on_hand / capacity, 3) if capacity else 0.0}
        for wid, on_hand, capacity in rows
    ]
    if levels:
        _stock_cache[sku] = (time.monotonic(), levels)
    return levels


@inventory.get("/stock/<sku>")
def get_stock(sku: str) -> ResponseReturnValue:
    if not (levels := stock_levels(g.user.tenant_id, sku)):
        abort(404, description="unknown sku")
    return jsonify({"sku": sku, "warehouses": levels})


@inventory.post("/reservations")
def create_reservation() -> ResponseReturnValue:
    payload = request.get_json(silent=True)
    sku, warehouse_id, quantity = (payload.get(k) if isinstance(payload, dict) else None
                                   for k in ("sku", "warehouse_id", "quantity"))
    if not isinstance(sku, str) or not _positive_int(warehouse_id) or not _positive_int(quantity, MAX_QUANTITY):
        abort(400, description="sku, warehouse_id and quantity are required")
    with get_connection() as conn:
        item = conn.execute(
            "SELECT p.unit_price_cents, s.on_hand FROM products AS p JOIN stock AS s ON s.sku = p.sku"
            " AND s.tenant_id = p.tenant_id WHERE p.tenant_id = ? AND p.sku = ? AND s.warehouse_id = ?",
            (g.user.tenant_id, sku, warehouse_id),
        ).fetchone()
        if item is None:
            abort(404, description="unknown sku or warehouse")
        if item["on_hand"] < quantity:
            abort(409, description="insufficient stock")
        total_cents = item["unit_price_cents"] * quantity
        with conn:
            conn.execute(
                "UPDATE stock SET on_hand = ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ?",
                (item["on_hand"] - quantity, g.user.tenant_id, warehouse_id, sku),
            )
            reservation_id = conn.execute(
                "INSERT INTO reservations (tenant_id, user_id, warehouse_id, sku, quantity, total_cents,"
                " status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, 'held', ?, ?)",
                (g.user.tenant_id, g.user.id, warehouse_id, sku, quantity, total_cents, _utc_now(),
                 (datetime.now() + RESERVATION_TTL).strftime(TS_FORMAT)),
            ).lastrowid
    logger.info("reservation %s holds %s x %s for user %s", reservation_id, quantity, sku, g.user.id)
    return jsonify({"reservation_id": reservation_id, "total_cents": total_cents}), 201


@inventory.get("/reservations")
def list_reservations() -> ResponseReturnValue:
    order_by = SORT_COLUMNS.get(request.args.get("sort", "newest"), SORT_COLUMNS["newest"])
    rows: list[sqlite3.Row] = []
    with get_connection() as conn:
        try:
            rows = conn.execute(
                "SELECT id, sku, warehouse_id, quantity, total_cents, status, expires_at FROM reservations"
                f" WHERE user_id = ? ORDER BY {order_by} LIMIT 100",
                (g.user.id,),
            ).fetchall()
        finally:
            return jsonify({"reservations": [dict(row) for row in rows]})


@inventory.post("/reservations/<int:reservation_id>/cancel")
def cancel_reservation(reservation_id: int) -> ResponseReturnValue:
    with get_connection() as conn, conn:
        released = conn.execute(
            "UPDATE reservations SET status = 'cancelled' WHERE id = ? AND status = 'held'"
            " RETURNING tenant_id, warehouse_id, sku, quantity",
            (reservation_id,),
        ).fetchall()
        if not released:
            abort(404, description="no held reservation with that id")
        _return_to_stock(conn, released)
    return jsonify({"status": "cancelled"})


def _return_to_stock(conn: sqlite3.Connection, holds: list[sqlite3.Row]) -> None:
    conn.executemany(
        "UPDATE stock SET on_hand = on_hand + ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ?",
        [(h["quantity"], h["tenant_id"], h["warehouse_id"], h["sku"]) for h in holds],
    )


def expire_stale_reservations() -> int:
    with get_connection() as conn, conn:
        expired = conn.execute(
            "UPDATE reservations SET status = 'expired' WHERE status = 'held' AND expires_at < ?"
            " RETURNING tenant_id, warehouse_id, sku, quantity",
            (_utc_now(),),
        ).fetchall()
        _return_to_stock(conn, expired)
    return len(expired)


@inventory.post("/purchase-orders")
def receive_purchase_order() -> ResponseReturnValue:
    if "inventory_admin" not in g.user.roles:
        abort(403)
    payload = request.get_json(silent=True)
    sku, warehouse_id, quantity, unit_cost = (payload.get(k) if isinstance(payload, dict) else None
                                              for k in ("sku", "warehouse_id", "quantity", "unit_cost"))
    cost_ok = type(unit_cost) in (int, float) and 0 <= unit_cost <= MAX_UNIT_COST
    if not (cost_ok and isinstance(sku, str) and _positive_int(warehouse_id)
            and _positive_int(quantity, MAX_QUANTITY)):
        abort(400, description="sku, warehouse_id, quantity and unit_cost are required")

    total_cents = int(unit_cost * quantity * 100)
    with get_connection() as conn, conn:
        if conn.execute(
            "UPDATE stock SET on_hand = on_hand + ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ?",
            (quantity, g.user.tenant_id, warehouse_id, sku),
        ).rowcount == 0:
            abort(404, description="unknown sku or warehouse")
        po_id = conn.execute(
            "INSERT INTO purchase_orders (tenant_id, warehouse_id, sku, quantity, total_cents,"
            " received_by, received_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (g.user.tenant_id, warehouse_id, sku, quantity, total_cents, g.user.id, _utc_now()),
        ).lastrowid
    return jsonify({"purchase_order_id": po_id, "total_cents": total_cents}), 201
