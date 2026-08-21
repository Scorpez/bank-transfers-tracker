"""Tests for parsing/normalization in wise_client, revolut_client and sheets."""

from __future__ import annotations

import textwrap

from src import wise_client, revolut_client, sheets


# --- Wise amount parsing ---

def test_parse_amount_positive():
    assert wise_client._parse_amount("<positive>+ 127.32 EUR</positive>") == (127.32, "EUR")


def test_parse_amount_negative_with_thousands():
    assert wise_client._parse_amount("- 2,344.31 EUR") == (2344.31, "EUR")


def test_parse_amount_garbage():
    assert wise_client._parse_amount("nonsense") is None


def test_normalize_activity_carries_kind_and_resource_id():
    act = {
        "createdOn": "2026-06-11T10:00:00Z",
        "title": "<strong>Ada Lovelace</strong>",
        "description": "",
        "resource": {"type": "TRANSFER", "id": 2185904308},
    }
    t = wise_client._normalize(act, 2750.0, "EUR")
    assert t["kind"] == "TRANSFER"
    assert t["resource_id"] == "2185904308"
    assert t["transaction_id"] == "wise-TRANSFER-2185904308"
    assert t["sender_name"] == "Ada Lovelace"


# --- Revolut CSV (ru and en locales) ---

RU_CSV = textwrap.dedent("""\
    Тип,Продукт,Дата начала,Дата выполнения,Описание,Сумма,Комиссия,Валюта,State,Остаток средств
    Переводы,Текущий,2026-02-17 09:00:00,2026-02-17 09:00:01,"Перевод, отправитель: KATHERINE JOHNSON",100.00,0.00,EUR,ВЫПОЛНЕНО,150.00
    Переводы,Текущий,2026-02-19 09:00:00,2026-02-19 09:00:01,В кошелек «EUR Life» из EUR,-250.00,0.00,EUR,ВЫПОЛНЕНО,0.00
    Пополнение,Текущий,2026-03-31 12:00:00,2026-03-31 12:00:01,Платеж от ADA LOVELACE,1500.00,0.00,EUR,ВЫПОЛНЕНО,1500.00
    Платеж по карте,Сбережения,2026-03-02 12:00:00,2026-03-02 12:00:01,Mercadona,-45.60,0.00,EUR,ВЫПОЛНЕНО,754.40
    Переводы,Текущий,2026-04-01 12:00:00,,Отменённый перевод,-10.00,0.00,EUR,ОТМЕНЕНО,754.40
""")


def test_read_statement_ru(tmp_path):
    p = tmp_path / "ru.csv"
    p.write_text(RU_CSV, encoding="utf-8")
    rows = revolut_client.read_statement(p)
    assert len(rows) == 4  # cancelled row dropped
    assert rows[0]["product"] == "Текущий"
    assert rows[0]["date"] == "2026-02-17"
    assert rows[0]["amount"] == 100.0
    assert rows[3]["description"] == "Mercadona"


EN_CSV = textwrap.dedent("""\
    Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance
    TRANSFER,Current,2026-02-17 09:00:00,2026-02-17 09:00:01,Transfer from KATHERINE JOHNSON,100.00,0.00,EUR,COMPLETED,150.00
""")


def test_read_statement_en(tmp_path):
    p = tmp_path / "en.csv"
    p.write_text(EN_CSV, encoding="utf-8")
    rows = revolut_client.read_statement(p)
    assert len(rows) == 1
    assert rows[0]["product"] == "Current"
    assert revolut_client.sender_name(rows[0]["description"]) == "KATHERINE JOHNSON"


def test_internal_and_topup_markers():
    assert revolut_client.is_internal("В кошелек «EUR Life» из EUR")
    assert revolut_client.is_internal("Вывод средств из кошелька")
    assert revolut_client.is_internal("Wise")
    assert revolut_client.is_internal("Пополнение счета Apple Pay с *7708")
    assert not revolut_client.is_internal("Пополнение с BIZUM")
    assert revolut_client.is_own_topup("Платеж от ADA LOVELACE")
    assert not revolut_client.is_own_topup("Перевод, отправитель: GRACE HOPPER")


def test_sender_name_extraction():
    assert revolut_client.sender_name("Перевод, отправитель: MARIE CURIE") == "MARIE CURIE"
    assert revolut_client.sender_name("Пополнение с BIZUM") == "Пополнение с BIZUM"


# --- sheets date/amount helpers ---

def test_sheets_date_roundtrip():
    assert sheets._parse_date("5/1/2026") == "2026-01-05"
    assert sheets._format_date("2026-01-05") == "5/1/2026"
    assert sheets._parse_date("") == ""


def test_sheets_amount_parsing():
    assert sheets._parse_amount("€2,344.31") == 2344.31
    assert sheets._parse_amount("") == 0.0
