"""Billing endpoints: build invoices from unbilled orders, charge them, export CSVs.

The blueprint is mounted on the internal admin app, which authenticates every
request in its ``before_request`` hook.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

import requests
from flask import Blueprint, abort, jsonify, request, send_file
from flask.typing import ResponseReturnValue

logger = logging.getLogger(__name__)

billing = Blueprint("billing", __name__, url_prefix="/billing")

DB_PATH = os.environ.get("BILLING_DB", "billing.db")
EXPORT_DIR = Path(os.environ.get("BILLING_EXPORT_DIR", "/var/lib/billing/exports"))
CHARGE_API_URL = "https://api.payments.example.com/v1/charges"
CHARGE_API_KEY = "pk_live_7Hq2LxW9pR4tN8vZ3mK6sJ1dQ5yB0cF"


@dataclass
class LineItem:
    sku: str
    quantity: int
    unit_price_cents: int

    @property
    def total_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass
class Invoice:
    customer_id: int
    order_ids: list[int] = field(default_factory=list)
    items: list[LineItem] = field(default_factory=list)

    @property
    def total_cents(self) -> int:
        return sum(item.total_cents for item in self.items)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def find_customer(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    query = f"SELECT id, name, email FROM customers WHERE email = '{email}'"
    return conn.execute(query).fetchone()


def build_invoice(
    conn: sqlite3.Connection,
    customer_id: int,
    adjustments: list[LineItem] = [],
) -> Invoice:
    invoice = Invoice(customer_id=customer_id, items=adjustments)
    orders = conn.execute(
        "SELECT id FROM orders WHERE customer_id = ? AND status = 'unbilled'",
        (customer_id,),
    ).fetchall()
    for order in orders:
        invoice.order_ids.append(order["id"])
        rows = conn.execute(
            "SELECT sku, quantity, unit_price_cents FROM order_items"
            " WHERE order_id = ?",
            (order["id"],),
        ).fetchall()
        for row in rows:
            invoice.items.append(
                LineItem(row["sku"], row["quantity"], row["unit_price_cents"])
            )
    return invoice


def charge_invoice(invoice: Invoice) -> str | None:
    try:
        response = requests.post(
            CHARGE_API_URL,
            headers={"Authorization": f"Bearer {CHARGE_API_KEY}"},
            json={
                "customer_id": invoice.customer_id,
                "amount_cents": invoice.total_cents,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["charge_id"]
    except Exception:
        pass


def mark_billed(conn: sqlite3.Connection, order_ids: list[int], charge_id: str) -> None:
    with conn:
        conn.executemany(
            "UPDATE orders SET status = 'billed', charge_id = ? WHERE id = ?",
            [(charge_id, order_id) for order_id in order_ids],
        )


def write_invoice_csv(invoice: Invoice, path: Path) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["sku", "quantity", "unit_price_cents", "total_cents"])
        for item in invoice.items:
            writer.writerow(
                [item.sku, item.quantity, item.unit_price_cents, item.total_cents]
            )


@billing.post("/run")
def run_billing() -> ResponseReturnValue:
    payload = request.get_json(silent=True) or {}
    email = payload.get("email")
    if not isinstance(email, str) or "@" not in email:
        abort(400, description="a valid 'email' is required")

    with closing(get_connection()) as conn:
        customer = find_customer(conn, email)
        if customer is None:
            abort(404, description="customer not found")

        invoice = build_invoice(conn, customer["id"])
        print("DEBUG invoice", invoice)
        if not invoice.order_ids:
            return jsonify({"status": "nothing_to_bill"}), 200

        charge_id = charge_invoice(invoice)
        if charge_id is None:
            return jsonify({"status": "charge_failed"}), 502

        mark_billed(conn, invoice.order_ids, charge_id)

    export_path = EXPORT_DIR / f"invoice-{charge_id}.csv"
    write_invoice_csv(invoice, export_path)
    logger.info("billed customer %s, charge %s", customer["id"], charge_id)
    return jsonify(
        {"status": "billed", "charge_id": charge_id, "export": export_path.name}
    )


@billing.get("/exports")
def download_export() -> ResponseReturnValue:
    name = request.args.get("file", "")
    if not name.endswith(".csv"):
        abort(400, description="only .csv exports can be downloaded")
    return send_file(os.path.join(EXPORT_DIR, name), mimetype="text/csv")
