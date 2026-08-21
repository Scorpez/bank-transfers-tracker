"""Parse Revolut CSV statements (Russian or English locale exports)."""
from __future__ import annotations

import csv
import re
from pathlib import Path

from . import config

# column aliases: ru export -> canonical
_COLS = {
    "type": ("Тип", "Type"),
    "product": ("Продукт", "Product"),
    "date": ("Дата начала", "Started Date"),
    "description": ("Описание", "Description"),
    "amount": ("Сумма", "Amount"),
    "currency": ("Валюта", "Currency"),
    "state": ("State", "Состояние"),
    "balance": ("Остаток средств", "Balance"),
}

_COMPLETED = ("ВЫПОЛНЕНО", "COMPLETED")
_CURRENT_PRODUCTS = ("Текущий", "Current")

# internal plumbing: pocket moves, transfers to own Wise, own-card top-ups
_INTERNAL_MARKERS = (
    "В кошелек", "Вывод средств из кошелька",
    "To pocket", "Withdrawal from pocket",
    "Пополнение счета Apple Pay", "Apple Pay Top-Up",
)
def _own_topup_markers() -> tuple[str, ...]:
    """Top-up descriptions that mean "the account holder moved their own money in".

    Derived from ACCOUNT_HOLDER_NAMES rather than hardcoded: the statement renders the
    name upper-cased, and the export language follows the account's locale.
    """
    return tuple(
        prefix + name.upper()
        for name in config.ACCOUNT_HOLDER_NAMES
        for prefix in ("Платеж от ", "Payment from ")
    )


def _pick(row: dict, key: str) -> str:
    for alias in _COLS[key]:
        if alias in row:
            return (row[alias] or "").strip()
    return ""


def read_statement(csv_path: str | Path) -> list[dict]:
    """Read a Revolut CSV export into normalized dicts."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Revolut CSV not found: {csv_path}")

    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            state = _pick(row, "state")
            if state and state.upper() not in _COMPLETED:
                continue
            amount_s = _pick(row, "amount")
            date_s = _pick(row, "date")[:10]
            if not amount_s:
                continue
            try:
                amount = float(amount_s)
            except ValueError:
                print(f"[Revolut] {csv_path.name}:{i} — skipping row with bad amount {amount_s!r}")
                continue
            if not re.match(r"\d{4}-\d{2}-\d{2}", date_s):
                print(f"[Revolut] {csv_path.name}:{i} — skipping row with bad date {date_s!r}")
                continue
            rows.append({
                "type": _pick(row, "type"),
                "product": _pick(row, "product"),
                "date": date_s,  # YYYY-MM-DD
                "description": _pick(row, "description"),
                "amount": amount,
                "currency": _pick(row, "currency"),
            })
    return rows


def is_internal(desc: str) -> bool:
    return desc == "Wise" or any(m in desc for m in _INTERNAL_MARKERS)


def is_own_topup(desc: str) -> bool:
    return any(m in desc for m in _own_topup_markers())


def is_current_product(product: str) -> bool:
    return product in _CURRENT_PRODUCTS


def sender_name(desc: str) -> str:
    """Extract the sender from a transfer description, else return it as-is."""
    for prefix in ("Перевод, отправитель: ", "Transfer from "):
        if desc.startswith(prefix):
            return desc[len(prefix):].strip()
    return desc
