"""Scheduled report exports: tenants schedule a daily CSV that a cron worker emails to them.

Auth middleware loads ``g.user`` (id, tenant_id, email); cron runs ``python -m sample_good_2``."""

import csv
import hashlib
import hmac
import io
import json
import logging
import os
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from flask import Blueprint, abort, g, jsonify, request
from flask.typing import ResponseReturnValue

logger = logging.getLogger(__name__)

exports = Blueprint("exports", __name__, url_prefix="/exports")

DB_PATH = os.environ.get("EXPORTS_DB", "exports.db")
MAIL_API_URL = os.environ.get("MAIL_API_URL", "https://mail.internal.example.com/v1/messages")
SIGNING_KEY = os.environ["EXPORT_SIGNING_KEY"].encode()  # required: fail fast at startup
SIGNING_KEY_ID = "exp-hmac-2026-10"  # published, lets the gateway pick the key during rotation
HTTP_TIMEOUT_SECONDS = (3.05, 20.0)
TS_FORMAT = "%Y-%m-%d %H:%M:%S"
LEASE = timedelta(minutes=10)  # comfortably above CLAIM_BATCH_SIZE x the HTTP timeout
RETRY_DELAY = timedelta(minutes=30)
CLAIM_BATCH_SIZE = 10
MAX_SCHEDULES_PER_TENANT = 25
REPORT_DAYS = 31
REPORT_COLUMNS = {"usage": ("day", "api_calls", "storage_mb"), "errors": ("day", "api_calls", "error_count")}


@dataclass(frozen=True)
class Schedule:
    id: int
    tenant_id: int
    report: str
    local_time: time
    tz: ZoneInfo
    recipient: str
    due_at: str


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    # IMMEDIATE takes the write lock up front, so concurrent writers queue instead of deadlocking.
    with closing(sqlite3.connect(DB_PATH, timeout=5.0, isolation_level="IMMEDIATE")) as conn:
        conn.row_factory = sqlite3.Row
        yield conn


def _ts(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(TS_FORMAT)


def next_run_after(now: datetime, local_time: time, tz: ZoneInfo) -> datetime:
    """First UTC instant after ``now`` at which the wall clock in ``tz`` reads ``local_time``."""
    local_day = now.astimezone(tz).date()
    candidate = datetime.combine(local_day, local_time, tzinfo=tz)
    if candidate.astimezone(timezone.utc) <= now:
        candidate = datetime.combine(local_day + timedelta(days=1), local_time, tzinfo=tz)
    return candidate.astimezone(timezone.utc)


@exports.post("/schedules")
def create_schedule() -> ResponseReturnValue:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400, description="expected a JSON object")
    report, at, tz_name = payload.get("report"), payload.get("local_time"), payload.get("timezone")
    if not isinstance(report, str) or report not in REPORT_COLUMNS:
        abort(400, description=f"report must be one of {sorted(REPORT_COLUMNS)}")
    if not isinstance(at, str) or not isinstance(tz_name, str) or len(tz_name) > 64:
        abort(400, description="local_time and timezone are required")
    try:
        local_time, tz = time.fromisoformat(at), ZoneInfo(tz_name)
    except (ValueError, ZoneInfoNotFoundError):
        abort(400, description="local_time must be HH:MM and timezone an IANA name")
    next_run = next_run_after(datetime.now(timezone.utc), local_time, tz)
    with get_connection() as conn, conn:
        cur = conn.execute(
            "INSERT INTO export_schedules (tenant_id, created_by, report, local_time, timezone, recipient,"
            " next_run_at) SELECT ?, ?, ?, ?, ?, ?, ? WHERE (SELECT COUNT(*) FROM export_schedules"
            " WHERE tenant_id = ?) < ?",
            (g.user.tenant_id, g.user.id, report, local_time.strftime("%H:%M"), tz.key, g.user.email,
             _ts(next_run), g.user.tenant_id, MAX_SCHEDULES_PER_TENANT),
        )
        created, schedule_id = cur.rowcount, cur.lastrowid
    if created == 0:
        abort(409, description=f"at most {MAX_SCHEDULES_PER_TENANT} schedules per tenant")
    return jsonify({"id": schedule_id, "next_run_at": _ts(next_run)}), 201


def claim_due(conn: sqlite3.Connection, now: datetime) -> list[Schedule]:
    with conn:
        rows = conn.execute(
            "UPDATE export_schedules SET leased_until = ? WHERE id IN (SELECT id FROM export_schedules"
            " WHERE next_run_at <= ? AND (leased_until IS NULL OR leased_until < ?) ORDER BY next_run_at"
            " LIMIT ?) RETURNING id, tenant_id, report, local_time, timezone, recipient, next_run_at",
            (_ts(now + LEASE), _ts(now), _ts(now), CLAIM_BATCH_SIZE),
        ).fetchall()
    return [
        Schedule(row["id"], row["tenant_id"], row["report"], time.fromisoformat(row["local_time"]),
                 ZoneInfo(row["timezone"]), row["recipient"], row["next_run_at"])
        for row in rows
    ]


def build_csv(conn: sqlite3.Connection, schedule: Schedule, now: datetime) -> str:
    columns = REPORT_COLUMNS[schedule.report]
    since = (now - timedelta(days=REPORT_DAYS)).date().isoformat()
    rows = conn.execute(
        f"SELECT {', '.join(columns)} FROM daily_usage WHERE tenant_id = ? AND day >= ? ORDER BY day",
        (schedule.tenant_id, since),
    ).fetchall()
    writer = csv.writer(buffer := io.StringIO())
    writer.writerow(columns)
    writer.writerows(tuple(row) for row in rows)
    return buffer.getvalue()


def deliver(schedule: Schedule, body: str) -> None:
    raw = json.dumps({"to": schedule.recipient, "subject": f"Your {schedule.report} report", "attachments": [
        {"filename": f"{schedule.report}.csv", "content_type": "text/csv", "content": body}]}).encode()
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": f"export-{schedule.id}-{schedule.due_at}",
        "X-Signature": hmac.new(SIGNING_KEY, raw, hashlib.sha256).hexdigest(),
        "X-Signature-Key-Id": SIGNING_KEY_ID,
    }
    response = requests.post(MAIL_API_URL, data=raw, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()


def run_due(now: datetime) -> tuple[int, int]:
    delivered = failed = 0
    with get_connection() as conn:
        # Sequential on purpose: the batch is capped and the mail gateway rate-limits per sender.
        for schedule in claim_due(conn, now):
            try:
                deliver(schedule, build_csv(conn, schedule, now))
            except requests.RequestException:
                logger.exception("export %s failed; retrying in %s", schedule.id, RETRY_DELAY)
                failed += 1
                # next_run_at (and so the idempotency key) stays put; the lease delays the retry.
                update = "UPDATE export_schedules SET leased_until = ? WHERE id = ?"
                params: tuple[object, ...] = (_ts(now + RETRY_DELAY), schedule.id)
            else:
                delivered += 1
                update = ("UPDATE export_schedules SET next_run_at = ?, leased_until = NULL,"
                          " last_delivered_at = ? WHERE id = ?")
                params = (_ts(next_run_after(now, schedule.local_time, schedule.tz)), _ts(now), schedule.id)
            with conn:
                conn.execute(update, params)
    return delivered, failed


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        delivered, failed = run_due(datetime.now(timezone.utc))
    except Exception:
        logger.exception("export run aborted")
        raise
    success_rate = delivered / (delivered + failed) if delivered + failed else 1.0
    print(f"delivered={delivered} failed={failed} success_rate={success_rate:.2f}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
