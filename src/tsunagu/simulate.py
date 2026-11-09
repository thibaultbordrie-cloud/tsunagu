"""The simulation: one loop over days, vectorised over customers.

Each day: send the planned campaigns (with holdout groups), let customers open, click,
unsubscribe or block, then let them buy. A campaign has a TRUE causal effect (set in the
scenario) on recipients only; holdouts never get it. Orders keep the label of why they
happened, but that label goes to the `truth` schema, not to the shop data, exactly like in
real life where nobody tells you which order a campaign really caused.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .campaigns import CATS, Campaign, plan
from .config import Scenario
from .events import Event, demand_index, events_between
from .people import NEVER, Customers, make_customers
from .universe import CATEGORY_WEIGHTS, MARKETS, Product, catalogue

SHIPPING = {"EUR": (4.90, 60.0), "JPY": (550.0, 8000.0), "TWD": (120.0, 1500.0)}   # fee, free above
HOUR_PROFILE = {   # share of orders by local hour, assumption
    "FR": [1, .5, .3, .2, .2, .4, 1, 2, 3, 4, 4.5, 5, 6, 5.5, 5, 5, 5, 5.5, 6.5, 7.5, 8, 7, 5, 3],
    "JP": [3, 1.5, .8, .4, .3, .5, 1, 2, 3, 3.5, 4, 4.5, 6.5, 5, 4, 4, 4, 4.5, 5, 6, 7.5, 8.5, 8, 6],
    "TW": [3, 1.5, .8, .4, .3, .4, .8, 1.5, 2.5, 3.5, 4, 4.5, 6, 5, 4, 4, 4, 4.5, 5, 6, 7.5, 8.5, 8.5, 6],
}
ORGANIC_SOURCES = {
    "FR": (["direct", "google", "instagram", "pinterest"], [0.42, 0.38, 0.14, 0.06]),
    "JP": (["direct", "google", "yahoo_japan", "instagram", "x_twitter"], [0.35, 0.3, 0.15, 0.12, 0.08]),
    "TW": (["direct", "google", "facebook", "instagram", "line_timeline"], [0.33, 0.3, 0.14, 0.13, 0.1]),
}


@dataclass
class Result:
    scenario: Scenario
    events: list[Event]
    products: list[Product]
    customers: Customers
    campaigns: list[Campaign]
    audience: pd.DataFrame
    orders: pd.DataFrame
    order_lines: pd.DataFrame
    line_daily: pd.DataFrame
    email_daily: pd.DataFrame
    demand: pd.DataFrame
    truth_orders: pd.DataFrame
    parameters: dict


def run(sc: Scenario) -> Result:
    rng = np.random.default_rng(sc.seed)
    days = (sc.end - sc.start).days + 1
    events = events_between(sc.start, sc.end)
    demand = {m: np.zeros(days) for m in MARKETS}
    demand_event = {m: [None] * days for m in MARKETS}
    for d in range(days):
        date = sc.start + dt.timedelta(days=d)
        for m in MARKETS:
            demand[m][d], demand_event[m][d] = demand_index(m, date, events)
    products = catalogue()
    product_by_id = {pp.product_id: pp for pp in products}
    pool_by_cat = {cat: [pp for pp in products if pp.category == cat] for cat in CATS}
    cust = make_customers(sc, rng, demand)
    campaigns = plan(sc, events)
    by_day: dict[int, list[Campaign]] = {}
    for c in campaigns:
        by_day.setdefault(c.day, []).append(c)
    event_by_code_day = {(e.market, e.code, d): e for e in events if e.kind == "commercial"
                         for d in range(max(0, (e.start - sc.start).days), min(days, (e.end - sc.start).days + 1))}

    n = cust.n
    market = cust.market
    is_m = {m: market == m for m in MARKETS}
    unsub_day = np.full(n, NEVER)
    complaint_day = np.full(n, NEVER)
    hard_bounce_day = np.full(n, NEVER)
    block_day = np.full(n, NEVER)
    recv = np.zeros((30, n), dtype=np.int16)
    last_open = np.full(n, -NEVER)
    last_click = np.full(n, -NEVER)
    last_click_campaign = np.zeros(n, dtype=np.int64)
    last_open_campaign = np.zeros(n, dtype=np.int64)
    boost_amount = np.zeros(n)
    boost_until = np.full(n, -1)
    boost_campaign = np.zeros(n, dtype=np.int64)
    # Order history before the window is unknown; assume 70 % of existing customers bought once
    # somewhere between sign-up and day one.
    pre = cust.signup_day < 0
    last_order = np.full(n, -NEVER)
    bought = pre & (rng.random(n) < 0.7)
    last_order[bought] = (cust.signup_day[bought] * rng.random(bought.sum())).astype(int)

    audience_parts = []
    click_rows = []
    orders, lines, truth = [], [], []
    line_daily, email_daily = [], []
    camp_by_id = {c.campaign_id: c for c in campaigns}
    order_seq = {m: 1000 for m in MARKETS}

    for d in range(days):
        slot = d % 30
        recv[slot] = 0
        msgs7 = recv[[(d - k) % 30 for k in range(1, 8)]].sum(axis=0)
        msgs30 = recv.sum(axis=0)
        churned = d > cust.lifetime_end_day
        eng = np.where(churned, cust.engagement * 0.3, cust.engagement)

        for c in by_day.get(d, []):
            m = c.market
            base = is_m[m] & (cust.signup_day <= d)
            if c.channel == "email":
                elig = (base & cust.email_opt_in & (unsub_day > d) & (complaint_day > d) & (hard_bounce_day > d))
                if c.segment == "engaged_90d":
                    elig &= (last_open >= d - 90) | (last_click >= d - 90)
                elif c.segment == "lapsed_180d":
                    elig &= last_order < d - 180
            else:
                elig = base & (cust.line_friend_day <= d) & (block_day > d)
            idx = np.where(elig)[0]
            if idx.size == 0:
                continue
            hold = rng.random(idx.size) < sc.holdout_rate
            r = idx[~hold]
            k = r.size
            th_open, th_click = sc.theme_effect[c.theme]
            fatigue = sc.open_decay_per_extra_message_7d ** np.maximum(0, msgs7[r] - 1)
            fav = np.where(cust.favourite_category[r] == c.category, sc.favourite_category_click_boost, 1.0)
            growth = 1 + sc.optout_growth_per_extra_message_30d[c.channel] * np.maximum(
                0, msgs30[r] - sc.optout_free_messages_30d[c.channel])
            zeros = np.zeros(k, dtype=bool)
            if c.channel == "email":
                hard = cust.bad_email[r]
                soft = ~hard & (rng.random(k) < sc.soft_bounce)
                delivered = ~hard & ~soft
                p_open = np.clip(sc.email_open[m] * eng[r] * fatigue * th_open, 0, 0.95)
                human = delivered & (rng.random(k) < p_open)
                machine = delivered & cust.apple_mail[r] & (rng.random(k) < sc.mpp_machine_open)
                p_click = np.clip(sc.email_click_to_open[m] * eng[r] * th_click * fav, 0, 0.9)
                click = human & (rng.random(k) < p_click)
                p_out = sc.unsubscribe * growth * np.where(human, 1.0, 1.5)
                unsub = delivered & (rng.random(k) < p_out)
                complaint = delivered & ~unsub & (rng.random(k) < sc.complaint * growth)
                hard_bounce_day[r[hard]] = d
                unsub_day[r[unsub]] = d
                complaint_day[r[complaint]] = d
                blocked = zeros
            else:
                hard = soft = zeros
                delivered = ~zeros
                p_imp = np.clip(sc.line_impression[m] * np.sqrt(eng[r]) * fatigue * th_open, 0, 0.97)
                human = rng.random(k) < p_imp
                machine = zeros
                p_click = np.clip(sc.line_click_to_impression[m] * eng[r] * th_click * fav, 0, 0.9)
                click = human & (rng.random(k) < p_click)
                blocked = rng.random(k) < sc.line_block * growth * np.where(human, 1.0, 1.3)
                block_day[r[blocked]] = d
                unsub = complaint = zeros
            recv[slot, r[delivered]] += 1
            last_open[r[human]] = d
            last_open_campaign[r[human]] = c.campaign_id
            clicked = r[click]
            last_click[clicked] = d
            last_click_campaign[clicked] = c.campaign_id
            # true causal effect, spread over the effect window
            mult = sc.event_campaign_effect if c.theme in ("event", "event_last_call") else 1.0
            b_click = sc.incremental_after_click[m] * mult / sc.effect_window_days
            b_view = sc.incremental_after_delivery / sc.effect_window_days
            amount = np.where(click, b_click, np.where(delivered, b_view, 0.0))
            active_boost = boost_until[r] >= d
            take = amount > np.where(active_boost, boost_amount[r], 0.0)
            tr = r[take]
            boost_amount[tr] = amount[take]
            boost_until[tr] = d + sc.effect_window_days - 1
            boost_campaign[tr] = c.campaign_id
            # click timing, for the e-mail tool's event log and for order times
            delay = np.minimum(rng.exponential(3.0, clicked.size), 70.0)
            extra = rng.poisson(0.35, clicked.size)
            for cid, h, e in zip(cust.customer_id[clicked], delay, extra):
                click_rows.append((c.campaign_id, int(cid), c.send_utc + dt.timedelta(hours=float(h)), int(1 + e)))
            audience_parts.append(pd.DataFrame({
                "campaign_id": np.int32(c.campaign_id),
                "customer_id": np.concatenate([cust.customer_id[r], cust.customer_id[idx[hold]]]).astype(np.int32),
                "is_holdout": np.concatenate([np.zeros(k, bool), np.ones(hold.sum(), bool)]),
                **{name: np.concatenate([arr, np.zeros(hold.sum(), bool)]) for name, arr in (
                    ("delivered", delivered), ("hard_bounce", hard), ("soft_bounce", soft),
                    ("human_open", human), ("machine_open", machine & ~human), ("clicked", click),
                    ("unsubscribed", unsub), ("complained", complaint), ("blocked", blocked))},
            }))

        # ---- purchases ----
        active = cust.signup_day <= d
        rate = np.zeros(n)
        for m in MARKETS:
            rate[is_m[m]] = sc.daily_order_rate[m] * demand[m][d]
        base_p = rate * cust.propensity * np.where(churned, sc.churned_activity, 1.0)
        boost = np.where(boost_until >= d, boost_amount, 0.0)
        p = np.clip(base_p + boost, 0, 0.5)
        buyers = np.where(active & (rng.random(n) < p))[0]
        date = sc.start + dt.timedelta(days=d)
        for b in buyers:
            m = market[b]
            mk = MARKETS[m]
            incremental = rng.random() < (boost[b] / p[b] if p[b] > 0 else 0)
            cause_campaign = int(boost_campaign[b]) if incremental else None
            # what the shop sees: last click with a UTM in the window, if the UTM survived
            utm = None
            if last_click[b] >= d - (sc.effect_window_days - 1) and rng.random() < sc.utm_capture:
                utm = camp_by_id[int(last_click_campaign[b])]
            # people who meant to buy anyway often use the last message as a shortcut to the shop:
            # a click, a UTM, and an order the campaign did not cause
            intent = False
            window_start = d - (sc.effect_window_days - 1)
            if (utm is None and not incremental and last_click[b] < window_start
                    and last_open[b] >= window_start and rng.random() < sc.intent_click):
                utm, intent = camp_by_id[int(last_open_campaign[b])], True
                last_click[b], last_click_campaign[b] = d, utm.campaign_id
            hours = np.array(HOUR_PROFILE[m])
            hour = int(rng.choice(24, p=hours / hours.sum()))
            local = dt.datetime(date.year, date.month, date.day, hour, int(rng.integers(0, 60)), int(rng.integers(0, 60)))
            if utm is not None:
                click_local = (utm.send_local if utm.day == d else None)
                if click_local is not None and local < click_local:
                    local = click_local + dt.timedelta(minutes=int(rng.integers(5, 240)))
                    if local.date() != date:
                        local = dt.datetime(date.year, date.month, date.day, 23, 59, 0)
            utc = local.replace(tzinfo=ZoneInfo(mk.timezone)).astimezone(dt.UTC).replace(tzinfo=None)
            if intent:
                click_rows.append((utm.campaign_id, int(cust.customer_id[b]),
                                   utc - dt.timedelta(minutes=int(rng.integers(2, 25))), 1))
            # basket
            n_items = 1 + min(int(rng.poisson(sc.extra_items_mean)), 5)
            w = np.array([CATEGORY_WEIGHTS[m][cat] for cat in CATS])
            w[cust.favourite_category[b]] *= 2.5
            chosen = {}
            for _ in range(n_items):
                cat = CATS[int(rng.choice(len(CATS), p=w / w.sum()))]
                pool = pool_by_cat[cat]
                pz = 1 / np.arange(1, len(pool) + 1) ** 0.7
                pr = pool[int(rng.choice(len(pool), p=pz / pz.sum()))]
                chosen[pr.product_id] = chosen.get(pr.product_id, 0) + (2 if rng.random() < sc.double_quantity else 1)
            cur = mk.currency
            subtotal = sum(product_by_id[pid].price(cur) * q for pid, q in chosen.items())
            ev_code = demand_event[m][d]
            ev = event_by_code_day.get((m, ev_code, d)) if ev_code else None
            code, discount = None, 0.0
            if ev is not None and ev.discount_code and (
                    (utm is not None and utm.event_code == ev.code) or rng.random() < 0.5):
                code = ev.discount_code
                discount = subtotal * sc.event_discount[m]
                discount = round(discount) if cur != "EUR" else round(discount, 2)
            fee, free_above = SHIPPING[cur]
            shipping = 0.0 if subtotal - discount >= free_above else fee
            total = round(subtotal - discount + shipping, 2)
            status = rng.choice(["paid", "refunded", "partially_refunded"],
                                p=[1 - sc.refunded - sc.partially_refunded, sc.refunded, sc.partially_refunded])
            order_seq[m] += 1
            oid = len(orders) + 1
            if utm is not None:
                source = "line" if utm.channel == "line" else "email"
                medium = "line_message" if utm.channel == "line" else "email"
                landing = (f"/{mk.language.split('-')[0]}?utm_source={source}&utm_medium={medium}"
                           f"&utm_campaign={m.lower()}-{utm.campaign_id}-{utm.theme}")
                referrer = None
            else:
                names, probs = ORGANIC_SOURCES[m]
                source = str(rng.choice(names, p=probs))
                landing = f"/{mk.language.split('-')[0]}" + ("" if source == "direct" else "/collections/all")
                referrer = None if source == "direct" else source
            orders.append((oid, f"#{m}{order_seq[m]}", int(cust.shop_customer_id[b]), cust.email[b], m, cur,
                           utc, local, round(subtotal, 2), discount, shipping, total, code, str(status),
                           landing, referrer))
            for ln, (pid, q) in enumerate(chosen.items(), start=1):
                pp = product_by_id[pid]
                lines.append((oid, ln, pid, pp.sku, q, pp.price(cur)))
            truth.append((oid, int(cust.customer_id[b]), "campaign_incremental" if incremental else "organic",
                          cause_campaign, utm.campaign_id if utm is not None else None, intent))
            last_order[b] = d

        # ---- daily account snapshots ----
        for m in ("JP", "TW"):
            friends = is_m[m] & (cust.line_friend_day <= d)
            blocks = int((friends & (block_day <= d)).sum())
            line_daily.append((m, date, int(friends.sum()), int(friends.sum()) - blocks, blocks))
        for m in MARKETS:
            subs = is_m[m] & cust.email_opt_in & (cust.signup_day <= d)
            black = subs & ((unsub_day <= d) | (complaint_day <= d) | (hard_bounce_day <= d))
            email_daily.append((m, date, int(subs.sum()), int(black.sum())))

    audience = pd.concat(audience_parts, ignore_index=True) if audience_parts else pd.DataFrame()
    clicks = pd.DataFrame(click_rows, columns=["campaign_id", "customer_id", "clicked_at_utc", "clicks"])
    if not audience.empty:
        clicks = clicks.groupby(["campaign_id", "customer_id"], as_index=False).agg(
            clicked_at_utc=("clicked_at_utc", "min"), clicks=("clicks", "sum"))
        audience = audience.merge(clicks, on=["campaign_id", "customer_id"], how="left")
        audience["clicked"] = audience["clicked"] | audience["clicks"].notna()
        audience["clicks"] = audience["clicks"].fillna(0).astype(np.int16)
    orders_df = pd.DataFrame(orders, columns=[
        "order_id", "order_name", "shop_customer_id", "email", "market", "currency", "created_at_utc",
        "created_at_local", "subtotal", "discount", "shipping", "total", "discount_code", "financial_status",
        "landing_site", "referring_site"])
    lines_df = pd.DataFrame(lines, columns=["order_id", "line_no", "product_id", "sku", "quantity", "unit_price"])
    truth_df = pd.DataFrame(truth, columns=["order_id", "customer_id", "cause", "causing_campaign_id",
                                            "last_click_campaign_id", "intent_click"])
    res = Result(
        scenario=sc, events=events, products=products, customers=cust, campaigns=campaigns,
        audience=audience, orders=orders_df, order_lines=lines_df,
        line_daily=pd.DataFrame(line_daily, columns=["market", "date", "followers", "targeted_reaches", "blocks"]),
        email_daily=pd.DataFrame(email_daily, columns=["market", "date", "subscribers", "blacklisted"]),
        demand=pd.DataFrame([(m, sc.start + dt.timedelta(days=d), float(demand[m][d]), demand_event[m][d])
                             for m in MARKETS for d in range(days)],
                            columns=["market", "date", "demand_index", "main_event"]),
        truth_orders=truth_df,
        parameters=asdict(sc),
    )
    return res
