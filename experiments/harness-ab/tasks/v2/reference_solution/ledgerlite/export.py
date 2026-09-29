"""CSV/JSON export of a fiscal-period statement, with privacy redaction,
category canonicalization, and audit logging."""

import csv
import io
import json
import os
import re
from datetime import datetime, timezone

from .categories import canonical_category
from .errors import E_EXPORT_EXISTS, E_EXPORT_FORMAT, LedgerError
from .statement import fiscal_period_bounds

_LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{12,19}(?!\d)")
_SSN_RE = re.compile(r"\bssn\b\D*(\d+)", re.IGNORECASE)


def redact(text: str) -> str:
    """Redact sensitive substrings from a free-text description.

    - Any run of 12-19 consecutive digits is replaced with "****" followed
      by its own last 4 digits.
    - The case-insensitive word "ssn" followed (with any non-digit
      separator, e.g. ": ", " #") by a run of digits has those digits
      replaced with the literal "SSN:REDACTED" (the whole "ssn ... digits"
      span becomes "SSN:REDACTED").
    """

    def _long_number(m):
        digits = m.group(0)
        return "****" + digits[-4:]

    text = _SSN_RE.sub("SSN:REDACTED", text)
    text = _LONG_NUMBER_RE.sub(_long_number, text)
    return text


def _format_amount_signed(cents: int) -> str:
    negative = cents < 0
    abs_cents = abs(cents)
    whole, frac = divmod(abs_cents, 100)
    sign = "-" if negative else ""
    return f"{sign}{whole}.{frac:02d}"


def _entries_for_period(store, period):
    period_start, period_end = fiscal_period_bounds(period)
    txs = [t for t in store.transactions if period_start <= t.date <= period_end]
    txs.sort(key=lambda t: (t.date, t.id))
    return period_start, period_end, txs


def _check_out_path(path: str, force: bool) -> None:
    if os.path.exists(path) and not force:
        raise LedgerError(E_EXPORT_EXISTS, f"output file already exists: {path!r}")


def _audit_log(store, fmt: str, period: str, count: int) -> None:
    log_path = os.path.join(os.path.dirname(os.path.abspath(store.path)) or ".", ".ledgerlite-audit.log")
    now_env = os.environ.get("LEDGERLITE_NOW")
    if now_env:
        ts = now_env
    else:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts}|export|{fmt}|{period}|{count}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def export_csv(store, period: str, path: str, force: bool = False) -> None:
    """Export the fiscal `period`'s transactions to `path` as semicolon-
    delimited CSV: header "id;date;description;category;amount", dates
    DD.MM.YYYY, amounts comma-decimal with a trailing "-" for expenses (none
    for income), descriptions redacted, categories canonicalized, encoded
    UTF-8 with a BOM, CRLF line endings.

    Raises LedgerError(E_EXPORT_EXISTS) if `path` already exists and
    `force` is False.
    """
    _check_out_path(path, force)
    _period_start, _period_end, txs = _entries_for_period(store, period)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(["id", "date", "description", "category", "amount"])
    for t in txs:
        amount = _format_amount_signed(t.amount_cents).replace(".", ",")
        writer.writerow(
            [
                t.id,
                t.date.strftime("%d.%m.%Y"),
                redact(t.description),
                canonical_category(t.category),
                amount,
            ]
        )

    with open(path, "wb") as f:
        f.write(b"\xef\xbb\xbf")
        f.write(buf.getvalue().encode("utf-8"))

    _audit_log(store, "csv", period, len(txs))


def export_json(store, period: str, path: str, force: bool = False) -> None:
    """Export the fiscal `period`'s transactions to `path` as JSON:
    {"schema": "ledgerlite.export/3", "period": {"start": ISO, "end": ISO},
    "entries": [{"amount": "12.34", "category": ..., "date": ISO,
    "description": ..., "id": ...}, ...]} with all object keys sorted,
    amounts as signed decimal strings, descriptions redacted, categories
    canonicalized.

    Raises LedgerError(E_EXPORT_EXISTS) if `path` already exists and
    `force` is False.
    """
    _check_out_path(path, force)
    period_start, period_end, txs = _entries_for_period(store, period)

    envelope = {
        "schema": "ledgerlite.export/3",
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "entries": [
            {
                "id": t.id,
                "date": t.date.isoformat(),
                "description": redact(t.description),
                "category": canonical_category(t.category),
                "amount": _format_amount_signed(t.amount_cents),
            }
            for t in txs
        ],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, sort_keys=True)
        f.write("\n")

    _audit_log(store, "json", period, len(txs))


def export(store, fmt: str, period: str, path: str, force: bool = False) -> None:
    """Dispatch to export_csv or export_json by `fmt` ("csv" or "json").

    Raises LedgerError(E_EXPORT_FORMAT) for any other `fmt`.
    """
    if fmt == "csv":
        export_csv(store, period, path, force=force)
    elif fmt == "json":
        export_json(store, period, path, force=force)
    else:
        raise LedgerError(E_EXPORT_FORMAT, f"unknown export format: {fmt!r}")
