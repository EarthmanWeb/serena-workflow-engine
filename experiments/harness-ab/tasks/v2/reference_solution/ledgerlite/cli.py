"""Command-line interface for ledgerlite."""

import argparse
import sys
from datetime import date

from .errors import E_SPLIT_WEIGHTS, LedgerError
from .export import export as do_export
from .money import format_cents, parse_amount
from .statement import build_statement, render_statement
from .store import Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledgerlite")
    parser.add_argument("--file", default="ledger.json", help="path to the ledger JSON file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_p = subparsers.add_parser("add", help="add a transaction")
    add_p.add_argument("--date", required=True, help="YYYY-MM-DD")
    add_p.add_argument("--description", required=True)
    add_p.add_argument("--amount", required=True, help="decimal amount, e.g. -12.34")
    add_p.add_argument("--category", required=True)

    list_p = subparsers.add_parser("list", help="list transactions")
    list_p.add_argument("--month", default=None, help="YYYY-MM")

    subparsers.add_parser("balance", help="print the ledger balance")

    split_p = subparsers.add_parser("split", help="add a split transaction")
    split_p.add_argument("--date", required=True, help="YYYY-MM-DD")
    split_p.add_argument("--description", required=True)
    split_p.add_argument("--total", required=True, help="decimal amount, e.g. -120.00")
    split_p.add_argument(
        "--share",
        action="append",
        required=True,
        dest="shares",
        metavar="CAT=WEIGHT",
        help="category=integer weight; may be repeated",
    )

    statement_p = subparsers.add_parser("statement", help="print the fiscal-period statement")
    statement_p.add_argument("--period", required=True, help="YYYY-MM")

    export_p = subparsers.add_parser("export", help="export a fiscal period")
    export_p.add_argument("--format", required=True, choices=["csv", "json"])
    export_p.add_argument("--period", required=True, help="YYYY-MM")
    export_p.add_argument("--out", required=True, help="output file path")
    export_p.add_argument("--force", action="store_true", help="overwrite an existing --out file")

    return parser


def _parse_shares(raw_shares: list[str]) -> dict:
    shares = {}
    for item in raw_shares:
        if "=" not in item:
            raise LedgerError(E_SPLIT_WEIGHTS, f"invalid --share entry: {item!r}")
        category, _, weight_text = item.partition("=")
        try:
            weight = int(weight_text)
        except ValueError:
            raise LedgerError(E_SPLIT_WEIGHTS, f"invalid --share weight: {item!r}")
        shares[category] = weight
    return shares


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    store = Store(args.file)

    try:
        store.load()

        if args.command == "add":
            tx_date = date.fromisoformat(args.date)
            amount_cents = parse_amount(args.amount)
            tx = store.add_transaction(tx_date, args.description, amount_cents, args.category)
            store.save()
            print(f"added {tx.id}: {tx.description} {format_cents(tx.amount_cents)} [{tx.category}]")
            return 0

        if args.command == "list":
            for tx in store.list_transactions(month=args.month):
                print(
                    f"{tx.id}  {tx.date.isoformat()}  {format_cents(tx.amount_cents)}  "
                    f"{tx.category}  {tx.description}"
                )
            return 0

        if args.command == "balance":
            print(format_cents(store.balance()))
            return 0

        if args.command == "split":
            tx_date = date.fromisoformat(args.date)
            total_cents = parse_amount(args.total)
            shares = _parse_shares(args.shares)
            children = store.add_split(tx_date, args.description, total_cents, shares)
            store.save()
            for tx in children:
                print(f"added {tx.id}: {tx.description} {format_cents(tx.amount_cents)} [{tx.category}]")
            return 0

        if args.command == "statement":
            stmt = build_statement(store, args.period)
            sys.stdout.write(render_statement(stmt))
            return 0

        if args.command == "export":
            do_export(store, args.format, args.period, args.out, force=args.force)
            print(f"exported {args.period} ({args.format}) to {args.out}")
            return 0

        parser.error(f"unknown command: {args.command}")
        return 2
    except LedgerError as e:
        print(f"error: {e.code}: {e.message}", file=sys.stderr)
        return 2
