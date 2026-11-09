"""Customers: who they are, which systems know them, and their hidden behaviour.

Hidden traits (engagement, purchase propensity, lifetime) drive the simulation and are only
exported to the `truth` schema. Each system (shop, email tool, LINE) gets its own view, keyed
its own way, the way a real CRM stack looks before anyone reconciles it.
"""
from __future__ import annotations

import datetime as dt
import unicodedata
from dataclasses import dataclass

import numpy as np
from faker import Faker

from .config import Scenario
from .universe import CATEGORIES, CATEGORY_WEIGHTS, MARKETS

CATS = list(CATEGORIES)


@dataclass
class Customers:
    n: int
    customer_id: np.ndarray        # internal, truth only
    market: np.ndarray             # "FR" / "JP" / "TW"
    signup_day: np.ndarray         # days from scenario start (can be negative)
    first_name: list
    last_name: list
    kana: list                     # furigana for Japanese customers, else None
    region: list
    email: list                    # canonical address
    email_as_stored_in_email_tool: list
    email_opt_in: np.ndarray
    bad_email: np.ndarray
    apple_mail: np.ndarray
    line_user_id: list             # None when not a LINE friend
    line_friend_day: np.ndarray    # day the customer added the account, large value if never
    line_linked: np.ndarray        # LINE id linked to the shop account (LINE Login)
    shop_customer_id: np.ndarray
    email_contact_id: np.ndarray   # 0 when the customer never opted in
    engagement: np.ndarray         # mean 1
    propensity: np.ndarray         # mean 1, heavy tail
    lifetime_end_day: np.ndarray
    favourite_category: np.ndarray  # index into CATS
    acquisition: np.ndarray


NEVER = 10**6


def _romanish(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if c.isascii() and c.isalnum())


def make_customers(sc: Scenario, rng: np.random.Generator, demand_by_market: dict[str, np.ndarray]) -> Customers:
    days = (sc.end - sc.start).days + 1
    rows = {k: [] for k in ("market", "signup", "first", "last", "kana", "region", "email", "stored",
                            "line_id", "line_day", "acq")}
    for m, count in sc.customers.items():
        mk = MARKETS[m]
        fk = Faker(mk.faker_locale)
        fk.seed_instance(sc.seed * 1000 + sum(map(ord, m)))
        n_before = int(round(count * sc.signed_up_before_start))
        before = -rng.integers(1, 730, n_before)
        # new sign-ups follow demand: more people arrive during sales and festivals
        w = demand_by_market[m] / demand_by_market[m].sum()
        during = rng.choice(days, count - n_before, p=w)
        signup = np.concatenate([before, during])
        rng.shuffle(signup)
        acq_choices = {"FR": (["organic_search", "instagram", "newsletter_popup", "referral", "paid_search"],
                              [0.32, 0.22, 0.2, 0.08, 0.18]),
                       "JP": (["organic_search", "instagram", "line_ads", "x_twitter", "referral"],
                              [0.3, 0.25, 0.2, 0.15, 0.1]),
                       "TW": (["line_ads", "instagram", "facebook", "organic_search", "referral"],
                              [0.3, 0.25, 0.2, 0.15, 0.1])}[m]
        acq = rng.choice(acq_choices[0], count, p=acq_choices[1])
        for i in range(count):
            if m == "JP":
                last, first = fk.last_name(), fk.first_name()
                kana = f"{fk.last_kana_name()} {fk.first_kana_name()}"
                local = f"{_romanish(fk.first_romanized_name())}.{_romanish(fk.last_romanized_name())}"
                region = fk.prefecture()
            elif m == "TW":
                last, first = fk.last_name(), fk.first_name()
                kana, local, region = None, "tw.member", fk.city()
            else:
                last, first = fk.last_name(), fk.first_name()
                kana, region = None, fk.city()
                local = f"{_romanish(first)}.{_romanish(last)}"
            email = f"{local or 'client'}.{len(rows['email']) + 1}@{mk.email_domain}"
            stored = email
            if rng.random() < sc.email_typo_variant:
                stored = (" " + email.upper()) if rng.random() < 0.5 else email.capitalize() + " "
            friend = rng.random() < sc.line_friend[m]
            line_id = "U" + rng.bytes(16).hex() if friend else None
            line_day = int(signup[i] + rng.geometric(1 / 30)) if friend else NEVER
            rows["market"].append(m)
            rows["signup"].append(int(signup[i]))
            rows["first"].append(first)
            rows["last"].append(last)
            rows["kana"].append(kana)
            rows["region"].append(region)
            rows["email"].append(email)
            rows["stored"].append(stored)
            rows["line_id"].append(line_id)
            rows["line_day"].append(line_day)
            rows["acq"].append(acq[i])

    n = len(rows["market"])
    market = np.array(rows["market"])
    opt = np.array([rng.random() < sc.email_opt_in[m] for m in market])
    apple = np.array([rng.random() < sc.apple_mail[m] for m in market])
    signup = np.array(rows["signup"])
    fav = np.empty(n, dtype=np.int64)
    for m in MARKETS:
        idx = np.where(market == m)[0]
        w = np.array([CATEGORY_WEIGHTS[m][c] for c in CATS])
        fav[idx] = rng.choice(len(CATS), idx.size, p=w / w.sum())
    line_ids = rows["line_id"]
    linked = np.array([lid is not None and rng.random() < sc.line_login_linked for lid in line_ids])
    contact_ids = np.where(opt, 100000 + rng.permutation(n), 0)
    engagement = rng.beta(2, 4, n) * 3                   # Beta(2,4) has mean 1/3
    propensity = rng.gamma(0.6, 1 / 0.6, n) * engagement ** sc.propensity_follows_engagement
    propensity /= propensity.mean()
    return Customers(
        n=n,
        customer_id=np.arange(1, n + 1),
        market=market,
        signup_day=signup,
        first_name=rows["first"], last_name=rows["last"], kana=rows["kana"], region=rows["region"],
        email=rows["email"], email_as_stored_in_email_tool=rows["stored"],
        email_opt_in=opt,
        bad_email=rng.random(n) < sc.bad_email,
        apple_mail=apple,
        line_user_id=line_ids,
        line_friend_day=np.array(rows["line_day"]),
        line_linked=linked,
        shop_customer_id=7_400_000_000 + rng.permutation(n) * 7 + 3,
        email_contact_id=contact_ids,
        engagement=engagement,
        propensity=propensity,
        lifetime_end_day=signup + rng.exponential(sc.mean_lifetime_days, n).astype(int),
        favourite_category=fav,
        acquisition=np.array(rows["acq"]),
    )


def day_to_date(sc: Scenario, day: int) -> dt.date:
    return sc.start + dt.timedelta(days=int(day))
