"""Tests for the categorization rules and sync dedup logic."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from src import sync, sheets


def _tx(name, amount, kind="TRANSFER", date="2026-06-11T10:00:00Z", rid="1"):
    return {"date": date, "amount": amount, "sender_name": name,
            "kind": kind, "resource_id": rid,
            "transaction_id": f"wise-{kind}-{rid}"}


# --- incoming rules ---

def test_incoming_skips_cashback():
    assert sync.categorize_wise_incoming(_tx("Cashback", 1.35, kind="BALANCE_CASHBACK")) is None


def test_incoming_skips_small():
    assert sync.categorize_wise_incoming(_tx("Katherine Johnson", 11.50)) is None
    assert sync.categorize_wise_incoming(_tx("Katherine Johnson", 20.0)) is None


def test_incoming_skips_own_money():
    assert sync.categorize_wise_incoming(_tx("Ada Lovelace", 500.0)) is None
    assert sync.categorize_wise_incoming(_tx("To EUR", 670.0)) is None


def test_incoming_elena_rent_vs_communal():
    assert sync.categorize_wise_incoming(_tx("Katherine Johnson", 1175.0))[0] == "Аренда"
    assert sync.categorize_wise_incoming(_tx("Katherine Johnson", 888.70))[0] == "Аренда"
    assert sync.categorize_wise_incoming(_tx("Katherine Johnson", 76.84))[0] == "Коммунальные"


def test_incoming_other_people_are_perevod():
    assert sync.categorize_wise_incoming(_tx("Grace Hopper", 500.0))[0] == "Перевод"


# --- outgoing rules ---

def test_outgoing_card_goes_to_aggregate():
    mode, month, _ = sync.categorize_wise_outgoing(_tx("Glovo", 23.80, kind="CARD_TRANSACTION"))
    assert (mode, month) == ("aggregate", "2026-06")


def test_outgoing_fine_stays_individual():
    mode, cat, _ = sync.categorize_wise_outgoing(
        _tx("Ajuntament de Barcelona", 226.56, kind="CARD_TRANSACTION"))
    assert (mode, cat) == ("individual", "Штраф")


@patch("src.sync.wise_client.get_transfer_destination", return_value="Revolut")
def test_outgoing_self_revolut_salary_and_allowance(mock_dest):
    assert sync.categorize_wise_outgoing(_tx("Ada Lovelace", 2750.0))[1] == "Зарплата"
    assert sync.categorize_wise_outgoing(_tx("Ada Lovelace", 1500.0))[1] == "Allowance"


@patch("src.sync.wise_client.get_transfer_destination", return_value="BBVA")
def test_outgoing_self_bbva_communal(mock_dest):
    assert sync.categorize_wise_outgoing(_tx("Ada Lovelace", 2755.0))[1] == "Коммунальные"


def test_outgoing_person_transfer():
    mode, cat, _ = sync.categorize_wise_outgoing(_tx("HEDY LAMARR ELLOUZE", 2344.31))
    assert (mode, cat) == ("individual", "Перевод")


def test_outgoing_salary_jar():
    assert sync.categorize_wise_outgoing(
        _tx("To Salary", 100.0, kind="BALANCE_TRANSACTION"))[1] == "Зарплата"


# --- dedup keys ---

def test_existing_keys_and_ids():
    rows = [
        {"row": 2, "date": "2026-06-29", "direction": "Расход", "amount": 150.0,
         "txid": "wise-TRANSFER-2218301310", "bank": "Wise", "counterparty": "x",
         "category": "", "comment": ""},
        {"row": 3, "date": "2026-06-29", "direction": "Расход", "amount": 150.0,
         "txid": "", "bank": "Wise", "counterparty": "x", "category": "", "comment": ""},
    ]
    keys = sheets.existing_keys(rows)
    # only the row WITHOUT txid contributes a fallback key (rows with IDs
    # dedup by ID, so an identical new transaction must not be dropped)
    assert keys == {("Wise", "2026-06-29", "Расход", 150.0)}
    assert sheets.existing_ids(rows) == {"wise-TRANSFER-2218301310"}


# --- revolut import: individuals + aggregate math ---

@patch("src.sync.sheets")
def test_sync_revolut_aggregates_and_individuals(mock_sheets, tmp_path):
    csv = tmp_path / "st.csv"
    csv.write_text(
        "Тип,Продукт,Дата начала,Дата выполнения,Описание,Сумма,Комиссия,Валюта,State,Остаток средств\n"
        'Переводы,Текущий,2026-05-10 09:00:00,,"Перевод, отправитель: MARIE CURIE",600.00,0,EUR,ВЫПОЛНЕНО,600\n'
        "Пополнение,Текущий,2026-05-11 09:00:00,,Платеж от ADA LOVELACE,150.00,0,EUR,ВЫПОЛНЕНО,900\n"
        "Переводы,Текущий,2026-05-12 09:00:00,,В кошелек «EUR Life» из EUR,-900.00,0,EUR,ВЫПОЛНЕНО,0\n"
        "Платеж по карте,Сбережения,2026-05-13 09:00:00,,Mercadona,-450.00,0,EUR,ВЫПОЛНЕНО,450\n"
        "Платеж по карте,Сбережения,2026-05-14 09:00:00,,Glovo,-50.00,0,EUR,ВЫПОЛНЕНО,400\n",
        encoding="utf-8")

    mock_sheets.INCOMING = "Приход"
    mock_sheets.OUTGOING = "Расход"
    mock_sheets.AGG_NAME = sheets.AGG_NAME
    mock_sheets.read_all.return_value = []
    mock_sheets.existing_keys.return_value = set()
    mock_sheets.append_transactions.return_value = 1

    sync.sync_revolut(csv_path=str(csv))

    # one individual row: Marie 600 (own top-up and internal move skipped)
    txs = mock_sheets.append_transactions.call_args[0][0]
    assert len(txs) == 1
    assert txs[0]["counterparty"] == "MARIE CURIE"
    assert txs[0]["category"] == "Перевод"

    # aggregate: spend 500 − top-ups 150 = 350 for 2026-05
    args = mock_sheets.upsert_aggregate.call_args[0]
    assert args[0] == "Revolut" and args[1] == "2026-05" and args[2] == 350.0


@patch("src.sync.sheets")
def test_sync_revolut_bizum_allowance(mock_sheets, tmp_path):
    csv = tmp_path / "st.csv"
    csv.write_text(
        "Тип,Продукт,Дата начала,Дата выполнения,Описание,Сумма,Комиссия,Валюта,State,Остаток средств\n"
        "Пополнение,Текущий,2026-01-30 09:00:00,,Пополнение с BIZUM,1500.00,0,EUR,ВЫПОЛНЕНО,800\n",
        encoding="utf-8")
    mock_sheets.INCOMING = "Приход"
    mock_sheets.OUTGOING = "Расход"
    mock_sheets.AGG_NAME = sheets.AGG_NAME
    mock_sheets.read_all.return_value = []
    mock_sheets.existing_keys.return_value = set()
    mock_sheets.append_transactions.return_value = 1

    sync.sync_revolut(csv_path=str(csv))
    txs = mock_sheets.append_transactions.call_args[0][0]
    assert txs[0]["category"] == "Allowance"


@patch("src.sync.sheets")
def test_bizum_that_is_not_the_configured_allowance_is_not_allowance(mock_sheets, tmp_path):
    """A BIZUM top-up of any OTHER amount must not be classified as the allowance.

    This is the test that distinguishes the configured rule from the hardcoded one it
    replaced. The old implementation matched `amount >= 800`, so 900.00 came back as
    "Allowance" and this assertion fails against it. The sibling test above passes under
    both implementations and therefore proves nothing on its own.
    """
    csv = tmp_path / "st.csv"
    csv.write_text(
        "Тип,Продукт,Дата начала,Дата выполнения,Описание,Сумма,Комиссия,Валюта,State,Остаток средств\n"
        "Пополнение,Текущий,2026-01-30 09:00:00,,Пополнение с BIZUM,900.00,0,EUR,ВЫПОЛНЕНО,900\n",
        encoding="utf-8")
    mock_sheets.INCOMING = "Приход"
    mock_sheets.OUTGOING = "Расход"
    mock_sheets.AGG_NAME = sheets.AGG_NAME
    mock_sheets.read_all.return_value = []
    mock_sheets.existing_keys.return_value = set()
    mock_sheets.append_transactions.return_value = 1

    sync.sync_revolut(csv_path=str(csv))
    txs = mock_sheets.append_transactions.call_args[0][0]
    # A top-up that is not the configured allowance is an internal card move, so it is
    # dropped entirely rather than appended under another category (sync.py:203).
    assert txs == []


# --- wise sync plumbing ---

@patch("src.sync.state")
@patch("src.sync.sheets")
@patch("src.sync.wise_client")
@patch("src.sync.config")
def test_sync_wise_skips_without_token(mock_config, mock_wise, mock_sheets, mock_state, capsys):
    mock_config.WISE_API_TOKEN = ""
    sync.sync_wise()
    assert "Skipped" in capsys.readouterr().out
    mock_wise.get_incoming_transactions.assert_not_called()


@patch("src.sync.state")
@patch("src.sync.sheets")
@patch("src.sync.wise_client")
@patch("src.sync.config")
def test_sync_wise_dedup_by_id(mock_config, mock_wise, mock_sheets, mock_state, capsys):
    mock_config.WISE_API_TOKEN = "tok"
    mock_state.get_last_sync.return_value = datetime(2026, 6, 1, tzinfo=timezone.utc)
    mock_state.load.return_value = {}
    mock_sheets.INCOMING = "Приход"
    mock_sheets.OUTGOING = "Расход"
    mock_sheets.AGG_NAME = sheets.AGG_NAME
    mock_sheets.read_all.return_value = []
    mock_sheets.existing_ids.return_value = {"wise-TRANSFER-1"}
    mock_sheets.existing_keys.return_value = set()
    mock_sheets.append_transactions.return_value = 0
    mock_wise.get_incoming_transactions.return_value = [_tx("Grace Hopper", 500.0, rid="1")]
    mock_wise.get_outgoing_transactions.return_value = []

    sync.sync_wise()
    assert mock_sheets.append_transactions.call_args[0][0] == []
