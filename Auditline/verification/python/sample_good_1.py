"""Billing endpoints: build invoices from unbilled orders, charge them, export CSVs.

The blueprint is mounted on the internal admin app, which authenticates every
request in its ``before_request`` hook.
"""

from __future__ import annotations

import csv
import hashlib
import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import requests
from flask import Blueprint, abort, jsonify, request, send_from_directory
from flask.typing import ResponseReturnValue

logger = logging.getLogger(__name__)

billing = Blueprint("billing", __name__, url_prefix="/billing")

DB_PATH = os.environ.get("BILLING_DB", "billing.db")
EXPORT_DIR = Path(os.environ.get("BILLING_EXPORT_DIR", "/var/lib/billing/exports"))
CHARGE_API_URL = "https://api.payments.example.com/v1/charges"
CHARGE_API_KEY = os.environ["CHARGE_API_KEY"]  # required: fail fast at startup
CHARGE_TIMEOUT_SECONDS = 10


class ChargeError(RuntimeError):
    """The payment provider rejected the charge or could not be reached."""


@dataclass(frozen=True)
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


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        yield conn


def find_customer_id(conn: sqlite3.Connection, email: str) -> int | None:
    row = conn.execute("SELECT id FROM customers WHERE email = ?", (email,)).fetchone()
    return None if row is None else int(row["id"])


def build_invoice(conn: sqlite3.Connection, customer_id: int) -> Invoice:
    """Collect every unbilled order line for one customer in a single query."""
    rows = conn.execute(
        """
        SELECT o.id AS order_id, i.sku, i.quantity, i.unit_price_cents
        FROM orders AS o
        JOIN order_items AS i ON i.order_id = o.id
        WHERE o.customer_id = ? AND o.status = 'unbilled'
        ORDER BY o.id
        """,
        (customer_id,),
    ).fetchall()
    invoice = Invoice(customer_id=customer_id)
    for row in rows:
        if not invoice.order_ids or invoice.order_ids[-1] != row["order_id"]:
            invoice.order_ids.append(row["order_id"])
        invoice.items.append(
            LineItem(row["sku"], row["quantity"], row["unit_price_cents"])
        )
    return invoice


def idempotency_key(invoice: Invoice) -> str:
    """Same customer and orders give the same key, so a retry never double-charges."""
    raw = f"{invoice.customer_id}:{','.join(map(str, invoice.order_ids))}"
    return hashlib.sha256(raw.encode()).hexdigest()


def charge_invoice(invoice: Invoice) -> str:
    """Charge the invoice total and return the provider's charge id."""
    try:
        response = requests.post(
            CHARGE_API_URL,
            headers={
                "Authorization": f"Bearer {CHARGE_API_KEY}",
                "Idempotency-Key": idempotency_key(invoice),
            },
            json={
                "customer_id": invoice.customer_id,
                "amount_cents": invoice.total_cents,
            },
            timeout=CHARGE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return str(response.json()["charge_id"])
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise ChargeError(f"charge failed for customer {invoice.customer_id}") from exc


def mark_billed(conn: sqlite3.Connection, order_ids: list[int], charge_id: str) -> None:
    with conn:
        conn.executemany(
            "UPDATE orders SET status = 'billed', charge_id = ? WHERE id = ?",
            [(charge_id, order_id) for order_id in order_ids],
        )


def write_invoice_csv(invoice: Invoice, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
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
    if not isinstance(email, str) or "@" not in email or len(email) > 254:
        abort(400, description="a valid 'email' is required")

    with get_connection() as conn:
        customer_id = find_customer_id(conn, email)
        if customer_id is None:
            abort(404, description="customer not found")

        invoice = build_invoice(conn, customer_id)
        if not invoice.order_ids:
            return jsonify({"status": "nothing_to_bill"}), 200

        try:
            charge_id = charge_invoice(invoice)
        except ChargeError:
            logger.exception("billing run failed for customer %s", customer_id)
            return jsonify({"status": "charge_failed"}), 502

        mark_billed(conn, invoice.order_ids, charge_id)

    export_path = EXPORT_DIR / f"invoice-{charge_id}.csv"
    write_invoice_csv(invoice, export_path)
    logger.info("billed customer %s, charge %s", customer_id, charge_id)
    return jsonify(
        {"status": "billed", "charge_id": charge_id, "export": export_path.name}
    )


@billing.get("/exports")
def download_export() -> ResponseReturnValue:
    name = request.args.get("file", "")
    if not name.endswith(".csv"):
        abort(400, description="only .csv exports can be downloaded")
    # send_from_directory rejects names that resolve outside EXPORT_DIR.
    return send_from_directory(EXPORT_DIR, name, mimetype="text/csv")
