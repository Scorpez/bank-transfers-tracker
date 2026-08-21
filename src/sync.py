"""Sync Wise (API) and Revolut (CSV) into one unified transactions sheet.

Classification rules, all driven by configuration rather than baked in here:
- incoming: skip cashback and transfers at or below SMALL_INCOMING_LIMIT; a configured
  rent payer above RENT_THRESHOLD is rent, below it is utilities, anyone else a transfer
- outgoing self-transfers are pass-through spending, split by destination account;
  a transfer matching ALLOWANCE_AMOUNT is an allowance rather than salary
- everyday card spending is not itemised: one monthly aggregate row per bank, except
  fines from configured municipal merchants, which stay individual
- Revolut CSV: only current-account rows count individually; pocket and internal moves
  are skipped as they are not real spending
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import wise_client, revolut_client, sheets, state, config

OWN_NAMES = config.ACCOUNT_HOLDER_NAMES
FINE_MERCHANTS = ("Ajuntament", "Generalitat")
INTERNAL_INCOMING = ("To EUR", "Cashback")
SMALL_INCOMING_LIMIT = 20.0
SYNC_OVERLAP = timedelta(days=3)


def categorize_wise_incoming(t: dict) -> tuple[str, str] | None:
    """(category, comment) for an incoming transaction, or None to skip."""
    name, amount = t["sender_name"], t["amount"]
    if t.get("kind") == "BALANCE_CASHBACK" or name in INTERNAL_INCOMING:
        return None
    if name in OWN_NAMES:
        return None  # own money coming back — internal
    if amount <= SMALL_INCOMING_LIMIT:
        return None
    if name in config.RENT_PAYER_NAMES:
        if config.RENT_THRESHOLD and amount >= config.RENT_THRESHOLD:
            return "Аренда", "monthly rent payment (reimbursement)"
        return "Коммунальные", ""
    return "Перевод", ""


def categorize_wise_outgoing(t: dict) -> tuple[str, str, str] | None:
    """('individual', category, comment) or ('aggregate', month, '') or None."""
    name, amount, kind = t["sender_name"], t["amount"], t.get("kind", "")

    if kind == "CARD_TRANSACTION":
        if any(m in name for m in FINE_MERCHANTS):
            return "individual", "Штраф", f"карта: {name}"
        return "aggregate", t["date"][:7], ""

    if name == "To Salary":
        return "individual", "Зарплата", "internal transfer to the Salary jar"

    if name in OWN_NAMES and kind == "TRANSFER":
        dest = wise_client.get_transfer_destination(t["resource_id"])
        if dest == "Revolut":
            if config.ALLOWANCE_AMOUNT and amount == config.ALLOWANCE_AMOUNT:
                return "individual", "Allowance", "recurring allowance to own Revolut account"
            return "individual", "Зарплата", "transfer to own Revolut account"
        if dest == "BBVA":
            return "individual", "Коммунальные", "utilities and parking (own BBVA account)"
        return "individual", "Зарплата", "transfer to own account (bank not identified)"

    return "individual", "Перевод", ""


def sync_wise():
    """Sync Wise transactions (both directions) into «Транзакции»."""
    if not config.WISE_API_TOKEN:
        print("[Wise] Skipped — no API token configured")
        return

    ws = sheets._get_worksheet()
    rows = sheets.read_all(ws)
    seen_ids = sheets.existing_ids(rows)
    seen_keys = sheets.existing_keys(rows)

    since = state.get_last_sync("wise") - SYNC_OVERLAP
    print(f"[Wise] Fetching transactions since {since.date()}")

    new_txs = []
    card_agg: dict[str, list] = defaultdict(lambda: [0.0, 0])

    for t in wise_client.get_incoming_transactions(since):
        if t["transaction_id"] in seen_ids:
            continue
        cat = categorize_wise_incoming(t)
        if cat is None:
            continue
        key = ("Wise", t["date"][:10], sheets.INCOMING, round(t["amount"], 2))
        if key in seen_keys:
            continue
        category, comment = cat
        new_txs.append({
            "date": t["date"][:10], "bank": "Wise", "direction": sheets.INCOMING,
            "counterparty": t["sender_name"], "category": category,
            "amount": t["amount"], "comment": comment, "txid": t["transaction_id"],
        })

    seen_cards = set(state.load().get("wise_seen_card_ids", []))
    new_card_ids: set[str] = set()
    for t in wise_client.get_outgoing_transactions(since):
        if (t["transaction_id"] in seen_ids or t["transaction_id"] in seen_cards
                or t["transaction_id"] in new_card_ids):
            continue
        decision = categorize_wise_outgoing(t)
        if decision is None:
            continue
        mode, a, b = decision
        if mode == "aggregate":
            card_agg[a][0] += t["amount"]
            card_agg[a][1] += 1
            new_card_ids.add(t["transaction_id"])
            continue
        key = ("Wise", t["date"][:10], sheets.OUTGOING, round(t["amount"], 2))
        if key in seen_keys:
            continue
        new_txs.append({
            "date": t["date"][:10], "bank": "Wise", "direction": sheets.OUTGOING,
            "counterparty": t["sender_name"], "category": a,
            "amount": t["amount"], "comment": b, "txid": t["transaction_id"],
        })

    added = sheets.append_transactions(new_txs, ws=ws)
    print(f"[Wise] Added {added} transactions" if added else "[Wise] No new transactions")

    # Known tradeoff: if we crash between the sheet write below and the state
    # save, the next run re-adds these cards (double count, visible and fixable).
    # The reverse order would silently drop them forever — worse.
    for month, (total, n) in sorted(card_agg.items()):
        existing = next((r["amount"] for r in rows
                         if r["counterparty"] == sheets.AGG_NAME["Wise"]
                         and r["date"][:7] == month), 0.0)
        result = sheets.upsert_aggregate(
            "Wise", month, round(existing + total, 2),
            f"повседневные карточные траты за {month} (детали в Wise)", rows=rows, ws=ws)
        print(f"[Wise] Aggregate {month}: {result} (+{total:.2f}, {n} card payments)")

    st = state.load()
    # preserve insertion order (recent last) so the cap evicts oldest first
    ordered = list(dict.fromkeys(st.get("wise_seen_card_ids", []) + sorted(new_card_ids)))
    st["wise_seen_card_ids"] = ordered[-1000:]
    state.save(st)
    state.set_last_sync("wise", datetime.now(timezone.utc))


def sync_revolut(csv_path: str | None = None):
    """Import a Revolut CSV statement into «Транзакции» (idempotent)."""
    from pathlib import Path

    if csv_path:
        csv_files = [Path(csv_path)]
    else:
        csv_dir = config.REVOLUT_CSV_DIR
        if not csv_dir.exists():
            print(f"[Revolut] Skipped — no CSV directory at {csv_dir}")
            return
        csv_files = sorted(csv_dir.glob("*.csv"))
        if not csv_files:
            print(f"[Revolut] No CSV files found in {csv_dir}")
            return

    ws = sheets._get_worksheet()
    rows = sheets.read_all(ws)
    seen_keys = sheets.existing_keys(rows)

    # merge all statements first: overlapping exports must not each recompute
    # (last-file-wins / partial-month overwrites). Union is a MULTISET — two
    # genuinely identical transactions in one statement (e.g. two €150 top-ups
    # the same day) must survive, so take the max per-file count of each row.
    from collections import Counter
    counts: Counter = Counter()
    samples: dict[tuple, dict] = {}
    for f in csv_files:
        print(f"[Revolut] Reading {f.name}")
        file_counts: Counter = Counter()
        for r in revolut_client.read_statement(f):
            key = (r["date"], r["type"], r["product"], r["description"], r["amount"])
            file_counts[key] += 1
            samples[key] = r
        for key, n in file_counts.items():
            counts[key] = max(counts[key], n)
    stmt = sorted(
        (samples[key] for key, n in counts.items() for _ in range(n)),
        key=lambda r: r["date"])

    # individual rows: money from other people into «Текущий», > €20
    new_txs = []
    for r in stmt:
        if not revolut_client.is_current_product(r["product"]):
            continue
        if r["amount"] <= SMALL_INCOMING_LIMIT:
            continue
        desc = r["description"]
        if revolut_client.is_internal(desc) or revolut_client.is_own_topup(desc):
            continue
        is_allowance = (
            "BIZUM" in desc.upper()
            and config.ALLOWANCE_AMOUNT
            and r["amount"] == config.ALLOWANCE_AMOUNT
        )
        if "Пополнение" in r["type"] and not is_allowance:
            continue  # small top-ups (own card via Bizum/Apple Pay) are internal
        key = ("Revolut", r["date"], sheets.INCOMING, round(r["amount"], 2))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        new_txs.append({
            "date": r["date"], "bank": "Revolut", "direction": sheets.INCOMING,
            "counterparty": revolut_client.sender_name(desc),
            "category": "Allowance" if is_allowance else "Перевод",
            "amount": r["amount"],
            "comment": "allowance через Bizum" if is_allowance else "",
            "txid": "",
        })
    added = sheets.append_transactions(new_txs, ws=ws)
    if added:
        print(f"[Revolut] Added {added} incoming transactions")

    # monthly aggregates: real spend (all products, minus internal moves)
    # minus own Wise top-ups, which are already counted as Wise расход
    spend: dict[str, float] = defaultdict(float)
    topups: dict[str, float] = defaultdict(float)
    for r in stmt:
        month, amt, desc = r["date"][:7], r["amount"], r["description"]
        if amt < 0 and not revolut_client.is_internal(desc):
            spend[month] += -amt
        elif amt > 0 and revolut_client.is_own_topup(desc):
            topups[month] += amt
    for month in sorted(spend):
        excess = round(spend[month] - topups[month], 2)
        if excess <= 0:
            continue
        result = sheets.upsert_aggregate(
            "Revolut", month, excess,
            f"траты Revolut за {month} сверх пополнений с Wise", rows=rows, ws=ws)
        if result != "unchanged":
            print(f"[Revolut] Aggregate {month}: {result} ({excess:.2f})")


def sync_all():
    """Run full sync for all sources."""
    print(f"=== Sync started at {datetime.now(timezone.utc).isoformat()} ===")
    sync_wise()
    sync_revolut()
    print("=== Sync complete ===")
