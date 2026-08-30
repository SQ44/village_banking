"""Restate every stored amount as an exact number of ngwee.

Balances written while money was held as a float can sit on values no currency
has — 7784.760000000002 — because adding floats does not land on two decimal
places. Reading such a column through the new `NUMERIC(12, 2)` type already
returns a clean Decimal, so the application behaves correctly without this
script. What it does not do is fix what is *written down*, and a ledger whose
stored figures differ from the figures it reports is not one an auditor can
sign off.

So this rewrites each amount to its exact 2dp value, using the same half-up
rounding the application now applies everywhere, and prints what it changed.
That listing is the artefact: it says precisely which rows moved, by how much,
and in which direction, so the restatement itself is reviewable rather than
silent.

    python scripts/migrate_money_to_decimal.py --dry-run   # report only
    python scripts/migrate_money_to_decimal.py             # apply

Safe to run twice: a value already exact is left alone.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decimal import ROUND_HALF_UP  # noqa: E402

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from app.money import money  # noqa: E402

# Every column that holds an amount, and the tables they live in. Rates are
# included: a rate stored as 12.000000000000002 is just as wrong to look at,
# even though it never becomes money on its own.
MONEY_COLUMNS: dict[str, tuple[str, ...]] = {
    "account": ("balance",),
    "transaction": ("amount",),
    "loan": ("principal", "outstanding_principal", "outstanding_interest"),
    "loaninstallment": ("principal_due", "interest_due"),
    "loanrequest": ("principal",),
    "groupfee": ("amount",),
    "interestaccrual": ("amount",),
    "savingsproduct": ("min_balance",),
    "groupsettings": ("min_monthly_contribution",),
}

# Most tables key on `id`; group settings hang off the group they belong to.
PRIMARY_KEYS: dict[str, str] = {"groupsettings": "group_id"}


RATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "loan": ("interest_rate_percent", "admin_fee_percent"),
    "loanrequest": ("interest_rate_percent",),
    "interestaccrual": ("annual_rate",),
    "savingsproduct": ("interest_rate",),
    "groupsettings": (
        "admin_fee_percent",
        "loan_interest_percent",
        "loan_limit_multiplier",
        "liquidity_max_outstanding_percent",
    ),
}


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n LIMIT 1"),
        {"n": table},
    ).fetchone()
    return row is not None


def _quantize(raw, places: str) -> Decimal:
    return Decimal(str(raw)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def restate(dry_run: bool) -> int:
    changed = 0
    inspected = 0
    net_by_table: dict[str, Decimal] = {}

    with engine.begin() as conn:
        is_sqlite = engine.dialect.name == "sqlite"
        for places, group in (("0.01", MONEY_COLUMNS), ("0.0001", RATE_COLUMNS)):
            for table, columns in group.items():
                if is_sqlite and not _table_exists(conn, table):
                    continue
                quoted = f'"{table}"'
                key = PRIMARY_KEYS.get(table, "id")
                for column in columns:
                    rows = conn.execute(
                        text(f"SELECT {key}, {column} FROM {quoted} WHERE {column} IS NOT NULL")
                    ).fetchall()
                    for row_id, raw in rows:
                        inspected += 1
                        current = Decimal(str(raw))
                        exact = _quantize(raw, places)
                        if current == exact:
                            continue
                        delta = exact - current
                        net_by_table[table] = net_by_table.get(table, Decimal(0)) + delta
                        changed += 1
                        print(
                            f"  {table}.{column} {key}={row_id}: {current} -> {exact}"
                            f"  (delta {delta:+})"
                        )
                        if not dry_run:
                            conn.execute(
                                text(f"UPDATE {quoted} SET {column} = :v WHERE {key} = :i"),
                                {"v": str(exact), "i": row_id},
                            )
        if dry_run:
            # Nothing should persist from a report-only run.
            conn.rollback()

    print()
    print(f"inspected {inspected} value(s); {changed} needed restating")
    if net_by_table:
        print("net change per table (should be a few ngwee at most):")
        for table, delta in sorted(net_by_table.items()):
            print(f"  {table}: {delta:+}")
    if dry_run:
        print("\nDRY RUN — nothing was written. Re-run without --dry-run to apply.")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = parser.parse_args()

    print(f"database: {engine.url}")
    print()
    restate(args.dry_run)


if __name__ == "__main__":
    main()
