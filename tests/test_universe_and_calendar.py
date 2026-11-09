import datetime as dt
import re

import pytest

from tsunagu.events import commercial_events, demand_index, events_between, public_holidays
from tsunagu.universe import catalogue, local_price

CJK = re.compile(r"[぀-ヿ一-鿿]")


def test_catalogue_is_trilingual_and_unique():
    products = catalogue()
    assert len(products) == 60
    assert len({p.sku for p in products}) == 60
    for p in products:
        assert p.name_fr and CJK.search(p.name_ja) and CJK.search(p.name_zh_hant)


def test_prices_follow_local_habits():
    for p in catalogue():
        assert int(p.price_jpy) % 100 == 80            # 2,980 yen style
        assert int(p.price_twd) % 100 == 90            # NT$590 style
        assert round(p.price_eur % 1, 2) == 0.90       # 16.90 EUR style
    assert local_price(16, "JPY", "JP") == 2980


def _event(year, market, code):
    return next(e for e in commercial_events(year) if e.market == market and e.code == code)


def test_taiwan_calendar():
    assert _event(2026, "TW", "double_11").end == dt.date(2026, 11, 11)
    assert _event(2026, "TW", "double_12").start == dt.date(2026, 12, 11)
    # New Year shopping stops two days before the first day of 春節 (17 Feb 2026)
    assert _event(2026, "TW", "lny_shopping").end == dt.date(2026, 2, 15)
    assert _event(2026, "TW", "lny_break").uplift < 1
    assert _event(2026, "TW", "qixi").end == dt.date(2026, 8, 19)
    assert _event(2026, "TW", "mid_autumn").end == dt.date(2026, 9, 24)   # day before 中秋節


def test_japan_and_france_calendar():
    assert _event(2026, "JP", "golden_week").start == dt.date(2026, 4, 29)
    assert _event(2026, "JP", "obon").uplift < 1
    assert _event(2025, "JP", "black_friday").start == dt.date(2025, 11, 28)
    assert _event(2026, "FR", "soldes_hiver").start == dt.date(2026, 1, 7)
    assert _event(2025, "FR", "soldes_ete").start == dt.date(2025, 6, 25)


def test_public_holidays_have_local_and_english_names():
    hol = public_holidays(2026)
    jp = [e for e in hol if e.market == "JP"]
    assert any(CJK.search(e.name_local) for e in jp)
    assert all(e.name_en.isascii() for e in hol)


def test_unknown_qixi_year_is_refused():
    with pytest.raises(ValueError):
        commercial_events(2031)


def test_demand_peaks_on_double_11():
    ev = events_between(dt.date(2025, 10, 1), dt.date(2025, 11, 30))
    peak, code = demand_index("TW", dt.date(2025, 11, 11), ev)
    normal, _ = demand_index("TW", dt.date(2025, 10, 8), ev)
    assert code == "double_11" and peak > 2 * normal


def test_local_names_do_not_depend_on_the_machine_locale(monkeypatch):
    for var in ("LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.setenv(var, "C.UTF-8")
    tw = [e for e in public_holidays(2026) if e.market == "TW"]
    assert any(e.name_local == "春節" for e in tw)
