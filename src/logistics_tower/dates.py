"""
Delivery-date helpers: the planning horizon (today + N days) and a tolerant parser
for the ways a dispatcher writes dates ("hoje", "amanhã", "quinta", "26/09", ISO).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from logistics_tower.config import settings

WEEKDAYS_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
_WEEKDAY_ALIASES: dict[str, int] = {
    "segunda": 0, "seg": 0, "monday": 0, "mon": 0,
    "terca": 1, "terça": 1, "ter": 1, "tuesday": 1, "tue": 1,
    "quarta": 2, "qua": 2, "wednesday": 2, "wed": 2,
    "quinta": 3, "qui": 3, "thursday": 3, "thu": 3,
    "sexta": 4, "sex": 4, "friday": 4, "fri": 4,
    "sabado": 5, "sábado": 5, "sab": 5, "saturday": 5, "sat": 5,
    "domingo": 6, "dom": 6, "sunday": 6, "sun": 6,
}  # fmt: skip
_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_BR_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$")
_PLUS_RE = re.compile(r"^(?:\+|d\+|em\s+)(\d{1,2})(?:\s*dias?)?$")


def today() -> date:
    """Operational 'today' (overridable with REFERENCE_DATE for demos and reproducible runs)."""
    return settings.reference_date or date.today()


def planning_days(days: int | None = None) -> list[date]:
    """Dates the WMS keeps orders for: today and the next `PLANNING_HORIZON_DAYS - 1` days."""
    n = days or settings.planning_horizon_days
    start = today()
    return [start + timedelta(days=i) for i in range(n)]


def label_for(d: date) -> str:
    """Human label used by the dashboard and the copilot: 'hoje (qui 25/09)', 'amanhã (sex 26/09)', 'sáb 27/09'."""
    delta = (d - today()).days
    short = f"{WEEKDAYS_PT[d.weekday()][:3]} {d.strftime('%d/%m')}"
    if delta == 0:
        return f"hoje ({short})"
    if delta == 1:
        return f"amanhã ({short})"
    return short


def parse_delivery_date(value: str | date | None, reference: date | None = None) -> date:
    """
    Accepts: None/'' / 'hoje' / 'today' -> today; 'amanhã'/'amanha'/'tomorrow' -> +1;
    'depois de amanhã' -> +2; '+2', 'd+2', 'em 2 dias'; weekday names in pt/en (next occurrence,
    today if it is that weekday); ISO 'YYYY-MM-DD'; 'DD/MM' or 'DD/MM/YYYY'.
    """
    base = reference or today()
    if value is None:
        return base
    if isinstance(value, date):
        return value

    text = str(value).strip().lower()
    text = text.replace("ã", "a").replace("á", "a").replace("é", "e").replace("ç", "c").replace("-feira", "")
    text = re.sub(r"\s+", " ", text)
    if text in {"", "hoje", "today", "hj"}:
        return base
    if text in {"amanha", "tomorrow", "amn"}:
        return base + timedelta(days=1)
    if text in {"depois de amanha", "day after tomorrow"}:
        return base + timedelta(days=2)

    m = _PLUS_RE.match(text)
    if m:
        return base + timedelta(days=int(m.group(1)))

    m = _ISO_RE.match(text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _BR_RE.match(text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else base.year
        if year < 100:
            year += 2000
        candidate = date(year, month, day)
        if not m.group(3) and candidate < base - timedelta(days=180):
            candidate = date(year + 1, month, day)
        return candidate

    key = text.replace("proxima ", "").replace("próxima ", "").replace("next ", "").strip()
    if key in _WEEKDAY_ALIASES:
        target = _WEEKDAY_ALIASES[key]
        ahead = (target - base.weekday()) % 7
        return base + timedelta(days=ahead)

    raise ValueError(f"Data inválida: {value!r} (use hoje, amanhã, um dia da semana, DD/MM ou YYYY-MM-DD)")
