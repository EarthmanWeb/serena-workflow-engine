"""Command-line interface for ledgerlite."""

import argparse
import sys
from datetime import date

from .errors import LedgerError
from .money import format_cents, parse_amount
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

    return parser


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

        parser.error(f"unknown command: {args.command}")
        return 2
    except LedgerError as e:
        print(f"error: {e.code}: {e.message}", file=sys.stderr)
        return 2
