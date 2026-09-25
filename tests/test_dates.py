"""Tests for delivery-date parsing and the planning horizon."""

from datetime import date, timedelta

import pytest

from logistics_tower.dates import label_for, parse_delivery_date, planning_days

REF = date(2026, 9, 25)  # a Friday


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, REF),
        ("", REF),
        ("hoje", REF),
        ("Hoje", REF),
        ("today", REF),
        ("amanhã", REF + timedelta(days=1)),
        ("amanha", REF + timedelta(days=1)),
        ("tomorrow", REF + timedelta(days=1)),
        ("depois de amanhã", REF + timedelta(days=2)),
        ("+2", REF + timedelta(days=2)),
        ("em 3 dias", REF + timedelta(days=3)),
        ("sexta", REF),  # same weekday -> today
        ("sexta-feira", REF),
        ("sábado", REF + timedelta(days=1)),
        ("segunda", REF + timedelta(days=3)),
        ("próxima quinta", REF + timedelta(days=6)),
        ("thursday", REF + timedelta(days=6)),
        ("27/09", date(2026, 9, 27)),
        ("27/09/2026", date(2026, 9, 27)),
        ("2026-10-01", date(2026, 10, 1)),
    ],
)
def test_parse_delivery_date(text, expected):
    assert parse_delivery_date(text, reference=REF) == expected


def test_parse_delivery_date_rejects_garbage():
    with pytest.raises(ValueError, match="Data inválida"):
        parse_delivery_date("semana que vem", reference=REF)


def test_planning_horizon_and_labels(monkeypatch):
    from logistics_tower.config import settings

    monkeypatch.setattr(settings, "reference_date", REF)
    days = planning_days()
    assert days == [REF, REF + timedelta(days=1), REF + timedelta(days=2)]
    assert label_for(days[0]).startswith("hoje (sex 25/09)")
    assert label_for(days[1]).startswith("amanhã (sáb 26/09)")
    assert label_for(days[2]) == "dom 27/09"
