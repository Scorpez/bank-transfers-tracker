# bank-transfers-tracker

Pulls transactions from two banks that have nothing in common, works out what each one
*was*, and keeps a spreadsheet in sync without creating duplicates.

It is a small tool with an awkward problem underneath it, which is why it has tests.

## The problem

Personal finances spread across two providers give you two incompatible views:

- **Wise** has a REST API, returns structured JSON, and knows a transfer's destination.
- **Revolut** (personal accounts) has no API. You export a CSV — and the column headers,
  the transaction-type words and the decimal punctuation all change with the account's
  locale.

Neither tells you what a transaction *meant*. A €1,500 transfer to your own account is not
income. A card payment to a supermarket is not worth its own row. Money arriving from the
person you share a flat with is rent when it is large and utilities when it is small.

So the work is not "call an API". It is: normalise two shapes into one, classify each row
against rules that are personal by nature, and stay idempotent across re-runs.

## Design notes

**Every personal rule is configuration, not code.** Which names count as your own, what a
recurring allowance looks like, who pays you rent and above what threshold — all of it comes
from the environment. The code ships knowing nothing about any particular person. That is
not decoration: the first version of this hardcoded real names and real amounts into
`sync.py`, and it was the reason the repo could not be published.

**The CSV parser is locale-tolerant by construction.** Column names are matched through an
alias table (`src/revolut_client.py`), rather than assuming an English export. The same file
handles Russian and English statements without a flag.

**Re-running is safe.** A three-day overlap window is re-fetched every sync deliberately —
banks backfill — and rows are deduplicated on a stable key before anything is written
(`src/state.py`, `src/sheets.py`). Running twice produces the same sheet.

**Card spending aggregates; transfers stay individual.** Two hundred supermarket rows tell
you nothing. One monthly total does. Transfers between named people are the opposite.

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env      # then fill it in
python main.py --help
```

`.env` holds credentials and the personal classification rules. It is gitignored, and
`.env.example` documents every value.

## Tests

```bash
pip install pytest && pytest
```

35 tests. They cover the parts that break quietly rather than loudly: locale-dependent CSV
parsing, the categorisation rules, deduplication, and aggregation arithmetic. Every fixture
value is fabricated — the names are famous scientists, and the amounts are invented.

## Layout

| Path | Does |
|---|---|
| `src/wise_client.py` | Wise REST API — balances, incoming and outgoing transactions |
| `src/revolut_client.py` | CSV statement parsing, locale-tolerant |
| `src/sync.py` | Normalisation, classification, aggregation |
| `src/sheets.py` | Google Sheets writes, deduplicated |
| `src/state.py` | Sync cursor, so re-runs stay cheap |
| `RESEARCH.md` | What was evaluated before building — including the approaches rejected |

`RESEARCH.md` is kept deliberately. The interesting part of this project was discovering
that Revolut's personal accounts have no API at all, which is what forced the CSV path.
