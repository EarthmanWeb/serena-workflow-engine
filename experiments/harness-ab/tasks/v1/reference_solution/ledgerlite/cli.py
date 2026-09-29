"""Command-line interface for ledgerlite."""

import argparse
import sys
from datetime import date

from .budget import budget_report
from .errors import LedgerError
from .money import format_cents, parse_amount
from .recurring import RecurringRule
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

    recurring_p = subparsers.add_parser("recurring", help="manage recurring transactions")
    recurring_sub = recurring_p.add_subparsers(dest="recurring_command", required=True)

    recurring_add_p = recurring_sub.add_parser("add", help="add a recurring rule")
    recurring_add_p.add_argument("--description", required=True)
    recurring_add_p.add_argument("--amount", required=True)
    recurring_add_p.add_argument("--category", required=True)
    recurring_add_p.add_argument("--frequency", required=True)
    recurring_add_p.add_argument("--start", required=True, help="YYYY-MM-DD")
    recurring_add_p.add_argument("--end", default=None, help="YYYY-MM-DD")

    recurring_sub.add_parser("list", help="list recurring rules")

    budget_p = subparsers.add_parser("budget", help="manage monthly category budgets")
    budget_sub = budget_p.add_subparsers(dest="budget_command", required=True)

    budget_set_p = budget_sub.add_parser("set", help="set a category budget")
    budget_set_p.add_argument("--category", required=True)
    budget_set_p.add_argument("--month", required=True, help="YYYY-MM")
    budget_set_p.add_argument("--limit", required=True)

    budget_report_p = budget_sub.add_parser("report", help="print the budget report")
    budget_report_p.add_argument("--month", required=True, help="YYYY-MM")

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

        if args.command == "recurring":
            if args.recurring_command == "add":
                amount_cents = parse_amount(args.amount)
                end = date.fromisoformat(args.end) if args.end else None
                rule = RecurringRule(
                    id="",
                    description=args.description,
                    amount_cents=amount_cents,
                    category=args.category,
                    frequency=args.frequency,
                    start=date.fromisoformat(args.start),
                    end=end,
                )
                rule = store.add_recurring(rule)
                store.save()
                print(
                    f"added {rule.id}: {rule.description} {format_cents(rule.amount_cents)} "
                    f"[{rule.category}] ({rule.frequency})"
                )
                return 0

            if args.recurring_command == "list":
                for rule in store.list_recurring():
                    print(
                        f"{rule.id}  {rule.frequency}  {rule.start.isoformat()}  "
                        f"{format_cents(rule.amount_cents)}  {rule.category}  {rule.description}"
                    )
                return 0

            parser.error(f"unknown recurring command: {args.recurring_command}")
            return 2

        if args.command == "budget":
            if args.budget_command == "set":
                limit_cents = parse_amount(args.limit)
                store.set_budget(args.category, args.month, limit_cents)
                store.save()
                print(f"budget set: {args.category} {args.month} {format_cents(limit_cents)}")
                return 0

            if args.budget_command == "report":
                lines = budget_report(store, args.month)
                print("CATEGORY  LIMIT  SPENT  REMAINING  STATUS")
                for line in lines:
                    print(
                        f"{line.category}  {format_cents(line.limit_cents)}  "
                        f"{format_cents(line.spent_cents)}  {format_cents(line.remaining_cents)}  "
                        f"{line.status}"
                    )
                return 0

            parser.error(f"unknown budget command: {args.budget_command}")
            return 2

        parser.error(f"unknown command: {args.command}")
        return 2
    except LedgerError as e:
        print(f"error: {e.code}: {e.message}", file=sys.stderr)
        return 2
