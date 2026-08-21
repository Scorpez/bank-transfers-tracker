"""Test environment.

`src.config` reads its values at import time, so these must be set before any test
module imports the package. pytest loads conftest first, which is what makes that work.
All values here are fabricated.
"""
import os

os.environ.setdefault("ACCOUNT_HOLDER_NAMES", "Ada Lovelace,Lovelace Ada")
os.environ.setdefault("ALLOWANCE_AMOUNT", "1500")
os.environ.setdefault("RENT_PAYER_NAMES", "Katherine Johnson")
os.environ.setdefault("RENT_THRESHOLD", "800")
os.environ.setdefault("WISE_API_TOKEN", "test-token")
os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet-id")
