"""Data-retention purge: move transactions outside the kept fiscal-period
window into archive files, per this project's archival policy."""

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone

from .errors import E_RETENTION_PERIODS, LedgerError
from .export import _format_amount_signed, redact
from .statement import fiscal_period_bounds
from .store import Store


@dataclass
class PurgeResult:
    archived: int = 0
    kept: int = 0
    archive_path: str | None = None


def _current_period_string(today: date) -> str:
    """Resolve `today` into its containing "YYYY-MM" fiscal period label.

    The fiscal period for a month starts on the 15th; a date on or after
    the 15th belongs to that calendar month's period, a date before the
    15th belongs to the previous calendar month's period.
    """
    if today.day >= 15:
        year, month = today.year, today.month
    else:
        if today.month == 1:
            year, month = today.year - 1, 12
        else:
            year, month = today.year, today.month - 1
    return f"{year:04d}-{month:02d}"


def _step_period_back(period: str) -> str:
    year, month = (int(p) for p in period.split("-"))
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _fiscal_year_of(d: date) -> int:
    """The fiscal year of the fiscal period containing date `d` — the
    year component of that period's "YYYY-MM" label (same rolling rule
    as _current_period_string, applied to an arbitrary date)."""
    period = _current_period_string(d)
    year_str, _month_str = period.split("-")
    return int(year_str)


def _archive_path_for(store_path: str, fiscal_year: int) -> str:
    directory = os.path.dirname(os.path.abspath(store_path)) or "."
    stem = os.path.splitext(os.path.basename(store_path))[0]
    return os.path.join(directory, f"{stem}.archive.{fiscal_year}.json")


def _entry_for(t) -> dict:
    return {
        "id": t.id,
        "date": t.date.isoformat(),
        "description": redact(t.description),
        "category": t.category,
        "amount": _format_amount_signed(t.amount_cents),
    }


def _audit_log(store: Store, archived_count: int) -> None:
    log_path = os.path.join(
        os.path.dirname(os.path.abspath(store.path)) or ".", ".ledgerlite-audit.log"
    )
    now_env = os.environ.get("LEDGERLITE_NOW")
    ts = now_env if now_env else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts}|purge|{archived_count}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def _write_archive(archive_path: str, fiscal_year: int, new_entries: list) -> None:
    existing_entries = []
    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing_entries = existing.get("entries", [])

    by_id = {e["id"]: e for e in existing_entries}
    for e in new_entries:
        by_id[e["id"]] = e

    merged = sorted(by_id.values(), key=lambda e: (e["date"], e["id"]))

    envelope = {
        "schema": f"ledgerlite.archive/3",
        "entries": merged,
    }
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, sort_keys=True)
        f.write("\n")


def purge(store: Store, keep_periods: int, today: date) -> "PurgeResult":
    """Remove every transaction outside the most recent `keep_periods`
    fiscal periods (counted back from the period containing `today`,
    which counts as the first kept period) from `store`, archiving each
    removed transaction by its fiscal year. Persists `store` before
    returning.
    """
    if not isinstance(keep_periods, int) or isinstance(keep_periods, bool) or keep_periods <= 0:
        raise LedgerError(
            E_RETENTION_PERIODS, f"keep_periods must be a positive integer: {keep_periods!r}"
        )

    current_period = _current_period_string(today)
    kept_periods = set()
    period = current_period
    for _ in range(keep_periods):
        kept_periods.add(period)
        period = _step_period_back(period)

    kept_bounds = [fiscal_period_bounds(p) for p in kept_periods]

    def in_kept_window(d: date) -> bool:
        return any(start <= d <= end for start, end in kept_bounds)

    to_keep = []
    to_archive = []
    for t in store.transactions:
        if in_kept_window(t.date):
            to_keep.append(t)
        else:
            to_archive.append(t)

    result = PurgeResult(archived=0, kept=len(to_keep), archive_path=None)

    if to_archive:
        by_year: dict = {}
        for t in to_archive:
            by_year.setdefault(_fiscal_year_of(t.date), []).append(t)

        last_path = None
        for fiscal_year, txs in sorted(by_year.items()):
            archive_path = _archive_path_for(store.path, fiscal_year)
            entries = [_entry_for(t) for t in txs]
            _write_archive(archive_path, fiscal_year, entries)
            last_path = archive_path

        result.archived = len(to_archive)
        result.archive_path = last_path
        _audit_log(store, result.archived)

    store.transactions = to_keep
    store.save()

    return result
