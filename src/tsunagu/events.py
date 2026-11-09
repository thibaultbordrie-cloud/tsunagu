"""Commercial calendar for France, Japan and Taiwan.

Two layers:
- public holidays, from the `holidays` package (local and English names);
- commercial moments that move online demand: 初売り, Golden Week, お中元, 雙11, 雙12,
  the shopping days before 春節, the soldes in France, and so on.

The uplift values are assumptions chosen to look plausible, not measured market data.
They are documented in docs/ASSUMPTIONS.md and every one is visible in the output table.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import holidays

# Qixi (七夕, 7th day of the 7th lunar month), checked against a lunar calendar library.
QIXI = {2024: dt.date(2024, 8, 10), 2025: dt.date(2025, 8, 29), 2026: dt.date(2026, 8, 19),
        2027: dt.date(2027, 8, 8), 2028: dt.date(2028, 8, 26)}


@dataclass(frozen=True)
class Event:
    market: str
    code: str
    name_local: str
    name_en: str
    kind: str          # "commercial" or "public_holiday"
    start: dt.date
    end: dt.date       # inclusive
    uplift: float      # multiplier on online demand while the event runs (can be < 1)
    discount_code: str | None = None


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def _black_friday(year: int) -> dt.date:
    return _nth_weekday(year, 11, 3, 4) + dt.timedelta(days=1)   # day after US Thanksgiving


def _soldes_start(year: int, month: int) -> dt.date:
    """French sales: 2nd Wednesday of January (1st if the 2nd falls after the 12th);
    last Wednesday of June (the one before if it falls after the 28th)."""
    if month == 1:
        second = _nth_weekday(year, 1, 2, 2)
        return second if second.day <= 12 else second - dt.timedelta(days=7)
    last = _last_weekday(year, 6, 2)
    return last if last.day <= 28 else last - dt.timedelta(days=7)


def _first_day(hol: holidays.HolidayBase, name: str, year: int) -> dt.date:
    days = sorted(d for d, n in hol.items() if d.year == year and n == name)
    if not days:
        raise ValueError(f"{name} not found for {year}")
    return days[0]


def commercial_events(year: int) -> list[Event]:
    d, td = dt.date, dt.timedelta
    yy = str(year)[2:]
    tw = holidays.TW(years=year, language=holidays.TW.default_language)
    cny = _first_day(tw, "春節", year)
    mid_autumn = _first_day(tw, "中秋節", year)
    bf = _black_friday(year)
    if year not in QIXI:
        raise ValueError(f"Qixi date unknown for {year}: add it to QIXI")
    qixi = QIXI[year]
    ev = [
        # Japan
        Event("JP", "hatsuuri", "初売り", "New Year sales", "commercial", d(year, 1, 1), d(year, 1, 3), 1.6, f"HATSU{yy}"),
        Event("JP", "valentine", "バレンタイン", "Valentine's Day", "commercial", d(year, 2, 7), d(year, 2, 14), 1.35),
        Event("JP", "white_day", "ホワイトデー", "White Day", "commercial", d(year, 3, 8), d(year, 3, 14), 1.3),
        Event("JP", "golden_week", "ゴールデンウィーク", "Golden Week", "commercial", d(year, 4, 29), d(year, 5, 5), 1.2, f"GW{yy}"),
        Event("JP", "mothers_day", "母の日", "Mother's Day", "commercial",
              _nth_weekday(year, 5, 6, 2) - td(days=7), _nth_weekday(year, 5, 6, 2), 1.4),
        Event("JP", "ochugen", "お中元", "Summer gift season", "commercial", d(year, 7, 1), d(year, 7, 15), 1.3),
        Event("JP", "obon", "お盆", "Obon holidays", "commercial", d(year, 8, 13), d(year, 8, 16), 0.85),
        Event("JP", "black_friday", "ブラックフライデー", "Black Friday", "commercial", bf, bf + td(days=3), 1.5, f"BF{yy}JP"),
        Event("JP", "oseibo", "お歳暮", "Winter gift season", "commercial", d(year, 12, 1), d(year, 12, 17), 1.25),
        Event("JP", "christmas", "クリスマス", "Christmas", "commercial", d(year, 12, 18), d(year, 12, 24), 1.5),
        # Taiwan
        Event("TW", "lny_shopping", "年貨採買", "Lunar New Year shopping", "commercial",
              cny - td(days=14), cny - td(days=2), 1.6, f"CNY{yy}"),
        Event("TW", "lny_break", "春節連假", "Lunar New Year break", "commercial", cny - td(days=1), cny + td(days=4), 0.6),
        Event("TW", "valentine", "西洋情人節", "Valentine's Day", "commercial", d(year, 2, 8), d(year, 2, 14), 1.3),
        Event("TW", "mothers_day", "母親節", "Mother's Day", "commercial",
              _nth_weekday(year, 5, 6, 2) - td(days=7), _nth_weekday(year, 5, 6, 2), 1.4),
        Event("TW", "618", "618購物節", "618 shopping festival", "commercial", d(year, 6, 16), d(year, 6, 18), 1.4, f"TW618{yy}"),
        Event("TW", "qixi", "七夕情人節", "Qixi Festival", "commercial", qixi - td(days=5), qixi, 1.3),
        Event("TW", "mid_autumn", "中秋送禮", "Mid-Autumn gifts", "commercial",
              mid_autumn - td(days=10), mid_autumn - td(days=1), 1.35, f"MOON{yy}"),
        Event("TW", "anniversary", "週年慶", "Anniversary sales season", "commercial", d(year, 10, 15), d(year, 11, 9), 1.2),
        Event("TW", "double_11", "雙11", "Double 11", "commercial", d(year, 11, 10), d(year, 11, 11), 2.2, f"DOUBLE11{yy}"),
        Event("TW", "double_12", "雙12", "Double 12", "commercial", d(year, 12, 11), d(year, 12, 12), 1.7, f"DOUBLE12{yy}"),
        Event("TW", "christmas", "聖誕節", "Christmas", "commercial", d(year, 12, 18), d(year, 12, 24), 1.3),
        # France
        Event("FR", "soldes_hiver", "Soldes d'hiver", "Winter sales", "commercial",
              _soldes_start(year, 1), _soldes_start(year, 1) + td(days=27), 1.3, f"SOLDES{yy}"),
        Event("FR", "saint_valentin", "Saint-Valentin", "Valentine's Day", "commercial", d(year, 2, 8), d(year, 2, 14), 1.2),
        Event("FR", "fete_des_meres", "Fête des mères", "Mother's Day", "commercial",
              _last_weekday(year, 5, 6) - td(days=7), _last_weekday(year, 5, 6), 1.3),
        Event("FR", "soldes_ete", "Soldes d'été", "Summer sales", "commercial",
              _soldes_start(year, 6), _soldes_start(year, 6) + td(days=27), 1.25, f"ETE{yy}"),
        Event("FR", "rentree", "Rentrée", "Back to school", "commercial", d(year, 8, 25), d(year, 9, 10), 1.15),
        Event("FR", "black_friday", "Black Friday", "Black Friday", "commercial", bf, bf + td(days=3), 1.6, f"BF{yy}FR"),
        Event("FR", "noel", "Noël", "Christmas", "commercial", d(year, 12, 1), d(year, 12, 24), 1.45),
    ]
    return ev


def public_holidays(year: int) -> list[Event]:
    out = []
    for market, cls in (("FR", holidays.FR), ("JP", holidays.JP), ("TW", holidays.TW)):
        # name the language: otherwise gettext follows the machine locale (LANG=C.UTF-8 on CI)
        local = cls(years=year, language=cls.default_language)
        english = cls(years=year, language="en_US")
        for day, name in sorted(local.items()):
            out.append(Event(market, "public_holiday", name, english.get(day, name), "public_holiday", day, day, 1.0))
    return out


def events_between(start: dt.date, end: dt.date) -> list[Event]:
    out = []
    for year in range(start.year, end.year + 1):
        out += [e for e in commercial_events(year) + public_holidays(year) if e.end >= start and e.start <= end]
    return out


# Weekday shape of online orders (Mon..Sun), assumption.
WEEKDAY_FACTOR = {
    "FR": (1.10, 1.02, 0.98, 0.96, 0.92, 0.88, 1.14),
    "JP": (0.95, 0.93, 0.94, 0.95, 1.00, 1.12, 1.11),
    "TW": (0.97, 0.95, 0.95, 0.96, 1.00, 1.09, 1.08),
}
# Month shape (Jan..Dec), assumption: quiet early spring and summer, strong Q4.
MONTH_FACTOR = (0.95, 0.88, 0.92, 0.95, 1.0, 0.95, 0.92, 0.88, 0.97, 1.02, 1.15, 1.30)


def demand_index(market: str, day: dt.date, events: list[Event]) -> tuple[float, str | None]:
    """Relative online demand for a market on a day, and the strongest commercial event running."""
    base = WEEKDAY_FACTOR[market][day.weekday()] * MONTH_FACTOR[day.month - 1]
    best, code = 1.0, None
    for e in events:
        if e.market == market and e.kind == "commercial" and e.start <= day <= e.end:
            if abs(e.uplift - 1) > abs(best - 1):
                best, code = e.uplift, e.code
    return base * best, code
