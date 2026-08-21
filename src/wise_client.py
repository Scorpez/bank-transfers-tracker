"""Fetch transfers from Wise personal account."""

from __future__ import annotations

import re
from datetime import datetime

import requests

from . import config

_STRIP_HTML = re.compile(r"<[^>]+>")

# Spanish bank codes (IBAN positions 5-8) for destination detection
BANK_BY_CODE = {"0182": "BBVA", "1583": "Revolut"}

_account_cache: dict[int, str] = {}


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.WISE_API_TOKEN}"}


def _get(url: str, **kwargs) -> requests.Response:
    """GET with a hard timeout and retries — the Wise API occasionally hangs."""
    kwargs.setdefault("timeout", 25)
    kwargs.setdefault("headers", _headers())
    last: Exception | None = None
    for _ in range(4):
        try:
            return requests.get(url, **kwargs)
        except requests.exceptions.Timeout as e:
            last = e
    raise last


def list_balances() -> list[dict]:
    """List all balance accounts (multi-currency jars) with their IDs and currencies."""
    url = f"{config.WISE_API_BASE}/v4/profiles/{config.WISE_PROFILE_ID}/balances?types=STANDARD"
    resp = _get(url)
    resp.raise_for_status()
    return resp.json()


def _get_tracked_currency() -> str:
    if not config.WISE_BALANCE_ID:
        raise RuntimeError("WISE_BALANCE_ID not set. Run: python main.py list-wise-balances")

    for b in list_balances():
        if str(b["id"]) == str(config.WISE_BALANCE_ID):
            return b.get("currency", "")
    raise RuntimeError(f"Balance {config.WISE_BALANCE_ID} not found in profile")


def _fetch_activities(since: datetime, until: datetime | None = None) -> list[dict]:
    """Fetch all activities from the API with pagination."""
    all_activities = []
    cursor = None

    while True:
        params: dict = {"size": 50, "since": since.strftime("%Y-%m-%dT%H:%M:%S.000Z")}
        if until:
            params["until"] = until.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if cursor:
            params["cursor"] = cursor

        url = f"{config.WISE_API_BASE}/v1/profiles/{config.WISE_PROFILE_ID}/activities"
        resp = _get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        activities = data.get("activities", [])
        if not activities:
            break

        all_activities.extend(activities)

        cursor = data.get("cursor")
        if not cursor:
            break

    return all_activities


def get_transfer_destination(transfer_id: str | int) -> str:
    """Destination bank for an outgoing transfer: 'BBVA', 'Revolut' or ''.

    Resolved via the target account's IBAN bank code; cached per account.
    """
    resp = _get(f"{config.WISE_API_BASE}/v1/transfers/{transfer_id}")
    if resp.status_code != 200:
        return ""
    acc_id = resp.json().get("targetAccount")
    if not acc_id:
        return ""
    if acc_id not in _account_cache:
        r2 = _get(f"{config.WISE_API_BASE}/v1/accounts/{acc_id}")
        iban = ""
        if r2.status_code == 200:
            iban = ((r2.json().get("details") or {}).get("iban") or "").replace(" ", "")
        bank = ""
        if iban.startswith("ES"):
            bank = BANK_BY_CODE.get(iban[4:8], "")
        _account_cache[acc_id] = bank
    return _account_cache[acc_id]


def get_incoming_transactions(since: datetime, until: datetime | None = None) -> list[dict]:
    """Fetch incoming (credit) transactions for the configured balance."""
    tracked_currency = _get_tracked_currency()
    activities = _fetch_activities(since, until)

    result = []
    for a in activities:
        primary_amount = a.get("primaryAmount", "")
        if "<positive>" not in primary_amount:
            continue

        parsed = _parse_amount(primary_amount)
        if not parsed:
            continue

        amount, currency = parsed
        if currency != tracked_currency:
            continue

        result.append(_normalize(a, amount, currency))

    return result


def get_outgoing_transactions(since: datetime, until: datetime | None = None) -> list[dict]:
    """Fetch outgoing (debit) transactions for the configured balance."""
    tracked_currency = _get_tracked_currency()
    activities = _fetch_activities(since, until)

    result = []
    for a in activities:
        primary_amount = a.get("primaryAmount", "")
        # Outgoing = no <positive> tag
        if "<positive>" in primary_amount:
            continue

        parsed = _parse_amount(primary_amount)
        if not parsed:
            continue

        amount, currency = parsed
        if currency != tracked_currency:
            continue
        if amount == 0:
            continue  # skip zero-amount checks (e.g. CARD_CHECK)

        result.append(_normalize(a, amount, currency))

    return result


def _parse_amount(html_amount: str) -> tuple[float, str] | None:
    """Parse amount string like '<positive>+ 127.32 EUR</positive>' into (127.32, 'EUR')."""
    text = _STRIP_HTML.sub("", html_amount).strip()
    text = text.lstrip("+-").strip()
    text = text.replace(",", "")
    parts = text.rsplit(" ", 1)
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), parts[1]
    except ValueError:
        return None


def _normalize(activity: dict, amount: float, currency: str) -> dict:
    """Normalize a Wise activity to our common format."""
    title = _STRIP_HTML.sub("", activity.get("title", ""))
    description = _STRIP_HTML.sub("", activity.get("description", ""))
    resource = activity.get("resource", {})

    return {
        "date": activity.get("createdOn", ""),
        "source": "Wise",
        "amount": amount,
        "currency": currency,
        "sender_name": title,
        "reference": description,
        "kind": resource.get("type", "UNKNOWN"),
        "resource_id": str(resource.get("id", "")),
        "transaction_id": f"wise-{resource.get('type', 'UNKNOWN')}-{resource.get('id', '')}",
        "balance_after": "",
    }
