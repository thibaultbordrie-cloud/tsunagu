"""Scenario parameters. Every behavioural number of the simulation lives here, in one place,
so it can be read, questioned and changed. They are assumptions, not market measurements.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace


def _by_market(fr, jp, tw):
    return {"FR": fr, "JP": jp, "TW": tw}


@dataclass(frozen=True)
class Scenario:
    name: str
    seed: int
    start: dt.date
    end: dt.date
    customers: dict = field(default_factory=lambda: _by_market(9000, 7000, 6000))
    signed_up_before_start: float = 0.6        # share of customers who already exist on day one

    # Consent and identity
    email_opt_in: dict = field(default_factory=lambda: _by_market(0.82, 0.55, 0.45))
    line_friend: dict = field(default_factory=lambda: _by_market(0.0, 0.62, 0.78))
    line_login_linked: float = 0.70             # LINE friends whose LINE id is linked to their shop account
    bad_email: float = 0.012                    # addresses that hard-bounce on first send
    email_typo_variant: float = 0.02            # contacts stored with a different case or stray spaces
    apple_mail: dict = field(default_factory=lambda: _by_market(0.45, 0.62, 0.48))

    # Email behaviour (per delivered message)
    email_open: dict = field(default_factory=lambda: _by_market(0.22, 0.16, 0.14))
    email_click_to_open: dict = field(default_factory=lambda: _by_market(0.12, 0.10, 0.09))
    mpp_machine_open: float = 0.92              # Apple Mail Privacy Protection pre-fetch rate
    soft_bounce: float = 0.006
    unsubscribe: float = 0.0006
    complaint: float = 0.00008

    # LINE behaviour (per delivered message)
    line_impression: dict = field(default_factory=lambda: _by_market(0.0, 0.68, 0.62))
    line_click_to_impression: dict = field(default_factory=lambda: _by_market(0.0, 0.07, 0.08))
    line_block: float = 0.0009

    # Fatigue: more messages, fewer opens and more opt-outs
    open_decay_per_extra_message_7d: float = 0.85
    optout_growth_per_extra_message_30d: dict = field(default_factory=lambda: {"email": 0.25, "line": 0.3})
    optout_free_messages_30d: dict = field(default_factory=lambda: {"email": 6, "line": 8})

    # Theme multipliers (open, click)
    theme_effect: dict = field(default_factory=lambda: {
        "newsletter": (1.0, 1.0), "event": (1.15, 1.3), "event_teaser": (1.05, 0.9),
        "event_last_call": (1.1, 1.2), "win_back": (0.7, 1.1), "new_arrivals": (1.05, 1.1)})
    favourite_category_click_boost: float = 1.3

    # Purchases
    daily_order_rate: dict = field(default_factory=lambda: _by_market(0.0030, 0.0027, 0.0031))
    mean_lifetime_days: int = 540               # after it, a customer mostly stops buying
    churned_activity: float = 0.1
    propensity_follows_engagement: float = 0.7   # engaged people also buy more (exponent)
    # TRUE causal effect of a campaign (the thing analysts try to measure):
    # extra purchase probability over the 3 days after the message.
    incremental_after_click: dict = field(default_factory=lambda: _by_market(0.025, 0.03, 0.035))
    incremental_after_delivery: float = 0.0002  # seen but not clicked
    event_campaign_effect: float = 1.4
    effect_window_days: int = 3
    holdout_rate: float = 0.05
    utm_capture: float = 0.85                    # clicks whose UTM survives to the order (devices, apps)
    intent_click: float = 0.35                   # buyers-anyway who click the last message they opened

    # Baskets
    extra_items_mean: float = 0.6
    double_quantity: float = 0.10
    event_discount: dict = field(default_factory=lambda: _by_market(0.15, 0.10, 0.12))
    refunded: float = 0.02
    partially_refunded: float = 0.01

    def with_(self, **kw) -> Scenario:
        return replace(self, **kw)


SCENARIOS = {
    # Two full commercial years ending before today: what bloc 2 builds the warehouse on.
    "standard": Scenario("standard", 42, dt.date(2025, 1, 1), dt.date(2026, 10, 31)),
    # Fast, for tests and CI. Covers Q4 so 雙11, Black Friday and Christmas are in it.
    "tiny": Scenario("tiny", 7, dt.date(2025, 9, 1), dt.date(2025, 12, 31),
                     customers=_by_market(700, 600, 500)),
}
