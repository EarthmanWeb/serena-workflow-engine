"""Bank-statement CSV import, with duplicate detection and row rejection
per this project's idempotency policy. The bank CSV follows this
project's own data interchange standard byte-for-byte (semicolon
delimiter, DD.MM.YYYY dates, comma-decimal signed amounts, BOM
tolerated) -- the same standard this project already applies to every
file it reads or writes for consumption outside the app."""

import csv
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from .categories import ALLOWED_CATEGORIES, canonical_category
from .errors import LedgerError
from .models import Transaction
from .store import Store

_DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
_AMOUNT_RE = re.compile(r"^(-)?(\d+),(\d{2})$")


@dataclass
class ImportResult:
    added: list = field(default_factory=list)
    skipped_duplicates: int = 0
    rejected: list = field(default_factory=list)


def _fingerprint(tx_date: date, amount_cents: int, description: str) -> str:
    raw = f"{tx_date.isoformat()}|{amount_cents}|{description}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _existing_fingerprints(store: Store) -> set:
    return {
        _fingerprint(t.date, t.amount_cents, t.description) for t in store.transactions
    }


def _parse_interchange_date(text: str) -> date:
    m = _DATE_RE.match((text or "").strip())
    if not m:
        raise ValueError(f"invalid date: {text!r}")
    day, month, year = (int(g) for g in m.groups())
    return date(year, month, day)


def _parse_interchange_amount(text: str) -> int:
    m = _AMOUNT_RE.match((text or "").strip())
    if not m:
        raise ValueError(f"invalid amount: {text!r}")
    sign, whole, frac = m.groups()
    cents = int(whole) * 100 + int(frac)
    return -cents if sign else cents


def import_bank_csv(store: Store, path: str) -> "ImportResult":
    """Import a bank-exported CSV of transactions into `store`.

    The file follows this project's data interchange standard: semicolon
    delimiter, header row followed by data rows, dates DD.MM.YYYY,
    signed comma-decimal amounts, UTF-8 with BOM tolerated. Each data
    row (after the header) has 4 fields: date, description, category,
    amount. A row that fails to parse or resolve to an allowed category
    is rejected (its 1-based data-row number recorded) rather than
    raising. A row whose fingerprint (see DOM_IDEMPOTENCY) already
    matches an existing (or already-imported-this-call) transaction is
    skipped, never re-added or merged.
    """
    result = ImportResult()
    seen_fingerprints = _existing_fingerprints(store)

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)

    if not rows:
        return result

    data_rows = rows[1:]

    for row_number, row in enumerate(data_rows, start=1):
        if len(row) != 4:
            result.rejected.append(row_number)
            continue

        raw_date, raw_description, raw_category, raw_amount = row

        try:
            tx_date = _parse_interchange_date(raw_date)
        except ValueError:
            result.rejected.append(row_number)
            continue

        try:
            amount_cents = _parse_interchange_amount(raw_amount)
        except ValueError:
            result.rejected.append(row_number)
            continue

        category = canonical_category(raw_category.strip())
        if category not in ALLOWED_CATEGORIES:
            result.rejected.append(row_number)
            continue

        fingerprint = _fingerprint(tx_date, amount_cents, raw_description)
        if fingerprint in seen_fingerprints:
            result.skipped_duplicates += 1
            continue

        tx = store.add_transaction(tx_date, raw_description, amount_cents, category)
        seen_fingerprints.add(fingerprint)
        result.added.append(tx)

    return result
