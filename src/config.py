from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


# Wise
WISE_API_TOKEN = _env("WISE_API_TOKEN", "")
WISE_PROFILE_ID = _env("WISE_PROFILE_ID", "")
WISE_BALANCE_ID = _env("WISE_BALANCE_ID", "")  # specific balance to track
WISE_API_BASE = _env("WISE_API_BASE", "https://api.wise.com")

# Revolut CSV import directory
REVOLUT_CSV_DIR = Path(_env("REVOLUT_CSV_DIR", "./revolut_csv"))

# Google Sheets
GOOGLE_SERVICE_ACCOUNT_JSON = _env("GOOGLE_SERVICE_ACCOUNT_JSON", "./service_account.json")
GOOGLE_SHEET_ID = _env("GOOGLE_SHEET_ID", "")

# State file for tracking last sync
STATE_FILE = Path(_env("STATE_FILE", "./state.json"))

# Account holder — the names this person's own transfers arrive under. Used to tell a
# movement between the user's OWN accounts apart from real income. Comma-separated,
# because banks spell the same person differently ("Ada Lovelace", "Lovelace Ada").
ACCOUNT_HOLDER_NAMES = tuple(
    n.strip() for n in _env("ACCOUNT_HOLDER_NAMES", "").split(",") if n.strip()
)

# A recurring fixed transfer that should be categorised as an allowance rather than
# salary. Set to 0 to disable the rule.
ALLOWANCE_AMOUNT = float(_env("ALLOWANCE_AMOUNT", "0") or 0)

# A recurring counterparty whose larger incoming payments are rent reimbursement and whose
# smaller ones are utilities. Names comma-separated; threshold splits the two categories.
# Leave RENT_PAYER_NAMES empty to disable the rule entirely.
RENT_PAYER_NAMES = tuple(
    n.strip() for n in _env("RENT_PAYER_NAMES", "").split(",") if n.strip()
)
RENT_THRESHOLD = float(_env("RENT_THRESHOLD", "0") or 0)

# A rent payer with no threshold silently misclassifies EVERY payment from that person as
# utilities and never as rent — a half-configured rule that looks configured. Fail loudly.
if RENT_PAYER_NAMES and not RENT_THRESHOLD:
    raise RuntimeError(
        "RENT_PAYER_NAMES is set but RENT_THRESHOLD is 0 or unset. "
        "Set a threshold, or clear RENT_PAYER_NAMES to disable the rule."
    )

