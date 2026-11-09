"""Campaign plan: what a CRM team would schedule for each market and channel.

Weekly newsletters, product drops, monthly win-back, and the teaser / launch / last call
around every big commercial moment. More messages around events means more fatigue,
which is one of the trade-offs the data lets you study.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from .config import Scenario
from .events import Event
from .universe import BRAND, CATEGORIES, MARKETS

CATS = list(CATEGORIES)

# (weekday, hour, minute, theme, every_n_weeks) per market and channel
CADENCE = {
    ("FR", "email"): [(1, 10, 0, "newsletter", 1), (4, 10, 0, "new_arrivals", 2)],
    ("JP", "email"): [(2, 12, 0, "newsletter", 1)],
    ("JP", "line"): [(4, 19, 0, "newsletter", 1), (6, 11, 0, "new_arrivals", 2)],
    ("TW", "line"): [(1, 20, 0, "newsletter", 1), (5, 12, 0, "new_arrivals", 1)],
    ("TW", "email"): [(0, 10, 0, "newsletter", 2)],
}
EVENT_HOUR = {("FR", "email"): (10, 0), ("JP", "email"): (10, 0), ("JP", "line"): (19, 30),
              ("TW", "line"): (20, 0), ("TW", "email"): (10, 0)}

TEMPLATES = {
    "fr": {"newsletter": "La lettre {brand} · {cat}", "new_arrivals": "Nouveautés {brand} · {cat}",
           "win_back": "Vous nous manquez : une attention pour vous",
           "event_teaser": "Bientôt : {event}", "event": "{event} : la sélection {brand}",
           "event_last_call": "Dernières heures : {event}"},
    "ja": {"newsletter": "今週のおすすめ：{cat}", "new_arrivals": "【新着】{cat}の新作が入荷しました",
           "win_back": "お久しぶりです。特別なご案内をお届けします",
           "event_teaser": "まもなく開始：{event}", "event": "【{event}】{brand}の特別セレクション",
           "event_last_call": "本日最終日：{event}"},
    "zh-Hant": {"newsletter": "本週推薦｜{cat}", "new_arrivals": "新品上架｜{cat}",
                "win_back": "好久不見，為您準備了一份心意",
                "event_teaser": "倒數開始｜{event}", "event": "【{event}】{brand}限定優惠",
                "event_last_call": "最後一天｜{event}"},
}


@dataclass(frozen=True)
class Campaign:
    campaign_id: int
    market: str
    channel: str
    theme: str
    event_code: str | None
    category: int | None
    day: int
    send_local: dt.datetime
    send_utc: dt.datetime
    name: str
    segment: str


def _name(market: str, theme: str, cat: int | None, event: Event | None) -> str:
    lang = MARKETS[market].language
    return TEMPLATES[lang][theme].format(
        brand=BRAND[lang], cat=CATEGORIES[CATS[cat]][lang] if cat is not None else "",
        event=event.name_local if event else "")


def plan(sc: Scenario, events: list[Event]) -> list[Campaign]:
    days = (sc.end - sc.start).days + 1
    big = [e for e in events if e.kind == "commercial" and e.uplift >= 1.2]
    slots: list[tuple] = []          # (day, market, channel, theme, event, hour, minute)
    event_days: set[tuple] = set()

    for e in big:
        for channel in MARKETS[e.market].channels:
            hour, minute = EVENT_HOUR[(e.market, channel)]
            primary = MARKETS[e.market].channels[0] == channel
            moments = [("event", e.start)]
            if primary:
                moments.append(("event_teaser", e.start - dt.timedelta(days=3)))
                if e.uplift >= 1.4 and e.end > e.start:
                    moments.append(("event_last_call", e.end))
            for theme, when in moments:
                d = (when - sc.start).days
                if 0 <= d < days:
                    slots.append((d, e.market, channel, theme, e, hour, minute))
                    event_days.add((d, e.market, channel))

    for d in range(days):
        date = sc.start + dt.timedelta(days=d)
        week = date.isocalendar().week
        for (market, channel), rules in CADENCE.items():
            for weekday, hour, minute, theme, every in rules:
                if date.weekday() == weekday and week % every == 0 and (d, market, channel) not in event_days:
                    slots.append((d, market, channel, theme, None, hour, minute))
        # monthly win-back e-mail on the first Thursday
        if date.weekday() == 3 and date.day <= 7:
            for market in ("FR", "JP"):
                slots.append((d, market, "email", "win_back", None, 10, 0))

    slots.sort(key=lambda s: (s[0], s[5], s[6], s[1], s[2]))
    out = []
    for i, (d, market, channel, theme, e, hour, minute) in enumerate(slots, start=1):
        date = sc.start + dt.timedelta(days=d)
        week = date.isocalendar().week
        cat = None if e is not None or theme == "win_back" else (week + i) % len(CATS)
        local = dt.datetime(date.year, date.month, date.day, hour, minute, tzinfo=ZoneInfo(MARKETS[market].timezone))
        segment = {"event_last_call": "engaged_90d" if channel == "email" else "all_friends",
                   "win_back": "lapsed_180d"}.get(theme, "all_subscribers" if channel == "email" else "all_friends")
        out.append(Campaign(
            campaign_id=i, market=market, channel=channel, theme=theme,
            event_code=e.code if e else None, category=cat, day=d,
            send_local=local.replace(tzinfo=None),
            send_utc=local.astimezone(dt.UTC).replace(tzinfo=None),
            name=_name(market, theme, cat, e), segment=segment))
    return out
