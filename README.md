# bank-transfers-tracker

[![tests](https://github.com/sevamrk/bank-transfers-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/sevamrk/bank-transfers-tracker/actions/workflows/ci.yml)

Pulls transactions from two banks that have nothing in common, works out what each one
*was*, and keeps a spreadsheet in sync without creating duplicates.

It's a small tool with an awkward problem underneath it, which is why it has tests.

> **In 30 seconds**
>
> | | |
> |---|---|
> | **What it does** | Pulls from two banks with nothing in common, works out what each transaction meant, and keeps one sheet in sync |
> | **The hard part** | Running it twice must not duplicate anything, and the overlap window that catches backfills is what makes that hard |
> | **Why it is here** | It is not AI. Bank APIs, locale-shifting CSV, reconciliation, and tests on all of it |
> | **What it admits** | Revolut has no personal API, so a human still downloads the file. Everything after that is automatic |

## The problem

Personal finances spread across two providers give you two incompatible views:

- **Wise** has a REST API, returns structured JSON, and knows a transfer's destination.
- **Revolut** (personal accounts) has no API. You export a CSV, and the column headers,
  the transaction-type words and the decimal punctuation all change with the account's
  locale.

Neither tells you what a transaction *meant*. A €1,500 transfer to your own account isn't
income. A card payment to a supermarket isn't worth its own row. Money arriving from the
person you share a flat with is rent when it's large and utilities when it's small.

The work isn't "call an API". It's: normalise two shapes into one, classify each row
against rules that are personal by nature, and stay idempotent across re-runs.

## How it works

<img src="docs/diagrams/architecture.svg" alt="Two bank feeds normalise into one shape, get classified by rules read from the environment, aggregate or stay individual, dedupe on a stable key, and land in a Google Sheet" width="820">

Running it twice produces the same sheet. That's the whole difficulty: the
overlap window has to exist, and it has to not create duplicates.

## Design notes

**Every personal rule is configuration, not code.** Which names count as your own, what a
recurring allowance looks like, who pays you rent and above what threshold. All of it comes
from the environment. The code ships knowing nothing about any particular person. That's
not decoration: the first version of this hardcoded real names and real amounts into
`sync.py`, and it was the reason the repo couldn't be published.

**The CSV parser is locale-tolerant by construction.** Column names are matched through an
alias table (`src/revolut_client.py`), rather than assuming an English export. The same file
handles Russian and English statements without a flag.

**Re-running is safe.** A three-day overlap window is re-fetched every sync deliberately. Banks backfill, and rows are deduplicated on a stable key before anything is written
(`src/state.py`, `src/sheets.py`). Running twice produces the same sheet.

**Card spending aggregates; transfers stay individual.** Two hundred supermarket rows tell
you nothing. One monthly total does. Transfers between named people are the opposite.

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env      # then fill it in
python main.py --help
```

`.env` holds credentials and the personal classification rules. It's gitignored, and
`.env.example` documents every value.

## Tests

```bash
pip install pytest && pytest
```

35 tests. They cover the parts that break quietly rather than loudly: locale-dependent CSV
parsing, the categorisation rules, deduplication, and aggregation arithmetic. Every fixture
value is fabricated, the names are famous scientists, and the amounts are invented.

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

## Make it yours

Four things, in this order:

1. `.env`, the account names, the allowance amount, who pays rent and above what
   threshold. All of it's yours and none of it's in the code.
2. `src/revolut_client.py`, the column alias table. If your export is in a third
   locale, add its headers here and nothing else changes.
3. `src/sync.py`, the classification rules. They encode one household's idea of what
   a transaction meant; yours will differ.
4. `src/sheets.py`, the sheet layout, if you want different columns.

## Limitations

| What it does not do | The detail |
|---|---|
| **Revolut still needs a human** | There is no personal API, so somebody downloads a CSV and drops it in a folder. Everything after that is automatic and that first step is not. A headless browser could do it and would break every time the export page moves |
| **Single-user by construction** | One `.env`, one sheet, one set of rules. Multi-tenant means moving the rules into a store and keying everything by owner, which is a different program |
| **Classification is rules, not a model** | A transfer that is rent one month and a loan repayment the next needs a human to say so. Rules were right here, because a misclassified row in your own accounts is worse than an unclassified one, but the ceiling is real |
| **Google Sheets is the weakest link** | It is the right output because it is what gets read, and the wrong store because a spreadsheet has no schema. The dedup key protects the rows. Nothing protects a column somebody drags |

## Provenance

Written for my own accounts, then rewritten for publication. Every personal rule that
used to be hardcoded is configuration now, which is both why it can be published and
the better design. The fixtures are fabricated: the names are famous scientists and
every amount is invented.
