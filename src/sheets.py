"""Read/append the unified «Транзакции» sheet.

Columns: A Дата | B Банк | C Направление | D Контрагент | E Категория
         F Сумма | G Комментарий | H ID (wise txn id or agg:<bank>:<YYYY-MM>)
"""

from __future__ import annotations

import re
from datetime import date

import gspread
from google.oauth2.service_account import Credentials

from . import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = config.GOOGLE_SHEET_ID
TX_SHEET = "Транзакции"

AGG_NAME = {
    "Wise": "Wise — повседневные траты (агрегат за месяц)",
    "Revolut": "Revolut — повседневные траты (агрегат за месяц)",
}

INCOMING = "Приход"
OUTGOING = "Расход"


def _get_spreadsheet() -> gspread.Spreadsheet:
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
    )
    return gspread.authorize(creds).open_by_key(SHEET_ID)


def _get_worksheet() -> gspread.Worksheet:
    return _get_spreadsheet().worksheet(TX_SHEET)


def _parse_amount(s: str) -> float:
    s = (s or "").replace("€", "").replace(",", "").strip()
    return float(s) if s else 0.0


def _parse_date(s: str) -> str:
    """d/m/yyyy -> ISO yyyy-mm-dd (returns '' if unparseable)."""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s or "")
    if not m:
        return ""
    d, mo, y = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def _format_date(iso: str) -> str:
    """ISO yyyy-mm-dd -> d/m/yyyy (sheet locale en_GB)."""
    y, m, d = iso.split("-")
    return f"{int(d)}/{int(m)}/{y}"


def read_all(ws: gspread.Worksheet | None = None) -> list[dict]:
    """All transaction rows with their 1-based sheet row numbers."""
    ws = ws or _get_worksheet()
    out = []
    for i, r in enumerate(ws.get_values("A2:H10000"), start=2):
        r = r + [""] * (8 - len(r))
        if not r[0]:
            continue
        out.append({
            "row": i,
            "date": _parse_date(r[0]),
            "bank": r[1],
            "direction": r[2],
            "counterparty": r[3],
            "category": r[4],
            "amount": _parse_amount(r[5]),
            "comment": r[6],
            "txid": r[7],
        })
    return out


def existing_keys(rows: list[dict]) -> set[tuple]:
    """Fallback dedup keys — only for rows that predate the ID column.

    Rows that carry a txid are deduplicated by ID alone; including them here
    would wrongly drop a legitimate new transaction that happens to share
    bank+date+direction+amount with an existing one.
    """
    return {(r["bank"], r["date"], r["direction"], round(r["amount"], 2))
            for r in rows if not r["txid"]}


def existing_ids(rows: list[dict]) -> set[str]:
    return {r["txid"] for r in rows if r["txid"]}


def append_transactions(txs: list[dict], ws: gspread.Worksheet | None = None) -> int:
    """Append transactions (dicts with iso date, bank, direction, counterparty,
    category, amount, comment, txid) at the bottom of the table."""
    if not txs:
        return 0
    ws = ws or _get_worksheet()
    values = [[
        _format_date(t["date"]), t["bank"], t["direction"], t["counterparty"],
        t["category"], t["amount"], t.get("comment", ""), t.get("txid", ""),
    ] for t in sorted(txs, key=lambda t: t["date"])]
    ws.append_rows(values, value_input_option="USER_ENTERED", table_range="A1")
    return len(values)


def upsert_aggregate(bank: str, month: str, amount: float, comment: str,
                     rows: list[dict] | None = None,
                     ws: gspread.Worksheet | None = None) -> str:
    """Create or update the monthly everyday-spend aggregate row for a bank.

    `month` is 'YYYY-MM'; `amount` is the absolute value for that month
    (idempotent on re-import). Returns 'added' | 'updated' | 'unchanged'.
    """
    ws = ws or _get_worksheet()
    rows = rows if rows is not None else read_all(ws)
    name = AGG_NAME[bank]
    for r in rows:
        if r["counterparty"] == name and r["date"][:7] == month:
            if abs(r["amount"] - amount) < 0.01:
                return "unchanged"
            ws.batch_update([
                {"range": f"F{r['row']}", "values": [[amount]]},
                {"range": f"G{r['row']}", "values": [[comment]]},
            ], value_input_option="USER_ENTERED")
            return "updated"
    y, m = month.split("-")
    last_day = min(28, date.today().day) if month == date.today().strftime("%Y-%m") else 28
    append_transactions([{
        "date": f"{y}-{m}-{last_day:02d}", "bank": bank, "direction": OUTGOING,
        "counterparty": name, "category": "Покупки", "amount": amount,
        "comment": comment, "txid": f"agg:{bank.lower()}:{month}",
    }], ws=ws)
    return "added"
