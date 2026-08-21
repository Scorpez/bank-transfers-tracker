#!/usr/bin/env python3
"""Bank Transfers Tracker — CLI entry point."""

from __future__ import annotations

import argparse
import sys

from src import sync, wise_client


def main():
    parser = argparse.ArgumentParser(description="Sync bank transfers to Google Sheets")
    subparsers = parser.add_subparsers(dest="command")

    # Sync command (Wise auto + Revolut from CSV dir)
    subparsers.add_parser("sync", help="Sync Wise (API) + Revolut (CSVs from revolut_csv/) to Google Sheets")

    # Wise: list balances to pick which one to track
    subparsers.add_parser("list-wise-balances", help="List Wise balance accounts (pick one to track)")

    # Revolut: import a specific CSV file
    import_parser = subparsers.add_parser("import-revolut", help="Import Revolut transactions from a CSV file")
    import_parser.add_argument("csv_file", help="Path to the Revolut CSV export")

    args = parser.parse_args()

    if args.command == "sync":
        sync.sync_all()

    elif args.command == "list-wise-balances":
        balances = wise_client.list_balances()
        print("\nWise balances:")
        for b in balances:
            amt = b.get("amount", {})
            print(f"  ID: {b['id']:<15} {amt.get('currency', '???'):>5}  {amt.get('value', 0):>12.2f}")
        print("\nSet WISE_BALANCE_ID in .env to the ID you want to track.")

    elif args.command == "import-revolut":
        sync.sync_revolut(csv_path=args.csv_file)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
