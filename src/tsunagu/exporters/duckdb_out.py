"""Write a simulation to DuckDB, one schema per system, the way the data would really arrive.

ref        markets, products, commercial calendar
raw_shop   Shopify-like customers, orders, line items (keyed by shop customer id and e-mail)
raw_email  Brevo-like contacts, campaigns with statistics, event log, daily list sizes
raw_line   LINE-like message insights (aggregates only), click URLs, followers, webhook
           follow / unfollow events, and the LINE Login links to shop accounts
raw_crm    the team's campaign plan and holdout groups, with each system's own identifiers
truth      what really happened: hidden traits, every message, why each order happened.
           Never read it to build the pipeline; use it to check your answers.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from ..simulate import Result
from ..universe import CATEGORIES, MARKETS

EMAIL_LIST_ID = {"FR": 11, "JP": 12, "TW": 13}


def _request_ids(res: Result) -> dict[int, str]:
    rng = np.random.default_rng(res.scenario.seed + 101)
    return {c.campaign_id: "{}-{}-{}-{}-{}".format(*[rng.bytes(n).hex() for n in (4, 2, 2, 2, 6)])
            for c in res.campaigns if c.channel == "line"}


def _email_campaign_ids(res: Result) -> dict[int, int]:
    return {c.campaign_id: 300 + i for i, c in enumerate(c for c in res.campaigns if c.channel == "email")}


def tables(res: Result) -> dict[str, pd.DataFrame]:
    sc, cust = res.scenario, res.customers
    rng = np.random.default_rng(sc.seed + 100)
    t: dict[str, pd.DataFrame] = {}
    cats = CATEGORIES

    # ---- ref ----
    t["ref.markets"] = pd.DataFrame([(m.code, m.country_en, m.currency, m.language, m.timezone, ",".join(m.channels))
                                     for m in MARKETS.values()],
                                    columns=["market", "country", "currency", "language", "timezone", "channels"])
    t["ref.products"] = pd.DataFrame([{
        "product_id": p.product_id, "sku": p.sku, "category": p.category,
        "category_fr": cats[p.category]["fr"], "category_ja": cats[p.category]["ja"],
        "category_zh_hant": cats[p.category]["zh-Hant"], "category_en": cats[p.category]["en"],
        "name_fr": p.name_fr, "name_ja": p.name_ja, "name_zh_hant": p.name_zh_hant,
        "price_eur": p.price_eur, "price_jpy": p.price_jpy, "price_twd": p.price_twd} for p in res.products])
    t["ref.calendar_events"] = pd.DataFrame([{
        "market": e.market, "code": e.code, "kind": e.kind, "name_local": e.name_local, "name_en": e.name_en,
        "start_date": e.start, "end_date": e.end, "demand_uplift": e.uplift, "discount_code": e.discount_code}
        for e in res.events]).sort_values(["market", "start_date", "code"]).reset_index(drop=True)

    # ---- raw_shop ----
    signup_ts = [dt.datetime.combine(sc.start + dt.timedelta(days=int(d)), dt.time(int(h), int(mi)))
                 for d, h, mi in zip(cust.signup_day, rng.integers(7, 23, cust.n), rng.integers(0, 60, cust.n))]
    t["raw_shop.customers"] = pd.DataFrame({
        "id": cust.shop_customer_id, "email": cust.email, "first_name": cust.first_name,
        "last_name": cust.last_name, "last_name_kana": cust.kana, "country_code": cust.market,
        "province": cust.region, "created_at": signup_ts, "accepts_marketing": cust.email_opt_in,
        "tags": [f"src:{a}" for a in cust.acquisition]})
    t["raw_shop.orders"] = res.orders.rename(columns={
        "order_id": "id", "order_name": "name", "shop_customer_id": "customer_id", "created_at_utc": "created_at",
        "subtotal": "subtotal_price", "discount": "total_discounts", "shipping": "shipping_price",
        "total": "total_price", "market": "country_code"}).assign(source_name="web")
    t["raw_shop.order_line_items"] = res.order_lines.rename(columns={"unit_price": "price"})

    # ---- raw_email ----
    has_contact = cust.email_contact_id > 0
    a = res.audience
    camp = pd.DataFrame([vars(c) for c in res.campaigns])
    a = a.merge(camp[["campaign_id", "channel", "market", "send_utc"]], on="campaign_id")
    ea = a[(a.channel == "email") & ~a.is_holdout]
    black = np.isin(cust.customer_id, ea.loc[ea.unsubscribed | ea.complained | ea.hard_bounce, "customer_id"].unique())
    contacts = pd.DataFrame({
        "id": cust.email_contact_id, "email": cust.email_as_stored_in_email_tool,
        "firstname": cust.first_name, "lastname": cust.last_name, "country": cust.market,
        "language": [MARKETS[m].language for m in cust.market], "created_at": signup_ts,
        "email_blacklisted": black,
        "list_id": [EMAIL_LIST_ID[m] for m in cust.market]})[has_contact]
    t["raw_email.contacts"] = contacts.reset_index(drop=True)
    email_ids = _email_campaign_ids(res)
    stats = ea.groupby("campaign_id").agg(
        sent=("delivered", "size"), delivered=("delivered", "sum"),
        human=("human_open", "sum"), machine=("machine_open", "sum"),
        clickers=("clicked", "sum"), unique_clicks=("clicks", "sum"),
        unsubscriptions=("unsubscribed", "sum"), hard_bounces=("hard_bounce", "sum"),
        soft_bounces=("soft_bounce", "sum"), complaints=("complained", "sum")).reset_index()
    ec = camp[camp.channel == "email"].merge(stats, on="campaign_id", how="left")
    ec[stats.columns] = ec[stats.columns].fillna(0)
    t["raw_email.campaigns"] = pd.DataFrame({
        "id": [email_ids[c] for c in ec.campaign_id], "name": ec.name, "subject": ec.name,
        "tag": ec.event_code.fillna(ec.theme),
        "list_id": [EMAIL_LIST_ID[m] for m in ec.market], "status": "sent", "sent_at": ec.send_utc,
        "sent": ec.sent.astype(int), "delivered": ec.delivered.astype(int),
        "unique_views": (ec.human + ec.machine).astype(int), "trackable_views": ec.human.astype(int),
        "apple_mpp_opens": ec.machine.astype(int), "unique_clicks": ec.unique_clicks.astype(int),
        "clickers": ec.clickers.astype(int), "unsubscriptions": ec.unsubscriptions.astype(int),
        "hard_bounces": ec.hard_bounces.astype(int), "soft_bounces": ec.soft_bounces.astype(int),
        "complaints": ec.complaints.astype(int)})
    stored = pd.Series(cust.email_as_stored_in_email_tool, index=cust.customer_id)
    ev = []
    for flag, name, lag in (("delivered", "delivered", 0.02), ("human_open", "opened", 2.0),
                            ("machine_open", "opened", 0.1), ("unsubscribed", "unsubscribed", 6.0),
                            ("hard_bounce", "hard_bounce", 0.01), ("soft_bounce", "soft_bounce", 0.01),
                            ("complained", "spam", 8.0)):
        sel = ea[ea[flag]]
        hours = np.minimum(rng.exponential(lag, len(sel)), 72)
        ev.append(pd.DataFrame({"campaign_id": [email_ids[c] for c in sel.campaign_id],
                                "email": stored.reindex(sel.customer_id).to_numpy(), "event": name,
                                "event_at": sel.send_utc.to_numpy() + pd.to_timedelta(hours, unit="h")}))
    clicked = ea[ea.clicked]
    ev.append(pd.DataFrame({"campaign_id": [email_ids[c] for c in clicked.campaign_id],
                            "email": stored.reindex(clicked.customer_id).to_numpy(), "event": "clicked",
                            "event_at": clicked.clicked_at_utc.to_numpy()}))
    t["raw_email.events"] = pd.concat(ev, ignore_index=True).sort_values("event_at").reset_index(drop=True)
    t["raw_email.lists"] = pd.DataFrame([(EMAIL_LIST_ID[m], f"Newsletter {m} (fictional)", m) for m in MARKETS],
                                        columns=["id", "name", "market"])
    t["raw_email.list_daily"] = res.email_daily.assign(list_id=res.email_daily.market.map(EMAIL_LIST_ID))[
        ["date", "list_id", "subscribers", "blacklisted"]]

    # ---- raw_line ----
    req = _request_ids(res)
    la = a[(a.channel == "line") & ~a.is_holdout]
    ls = la.groupby("campaign_id").agg(delivered=("delivered", "sum"), unique_impression=("human_open", "sum"),
                                       unique_click=("clicked", "sum"), clicks=("clicks", "sum")).reset_index()
    lc = camp[camp.channel == "line"].merge(ls, on="campaign_id", how="left")
    lc[ls.columns] = lc[ls.columns].fillna(0)
    t["raw_line.message_insights"] = pd.DataFrame({
        "request_id": [req[c] for c in lc.campaign_id], "account": lc.market, "sent_at": lc.send_utc,
        "delivered": lc.delivered.astype(int), "unique_impression": lc.unique_impression.astype(int),
        "unique_click": lc.unique_click.astype(int)})
    t["raw_line.message_clicks"] = pd.DataFrame({
        "request_id": [req[c] for c in lc.campaign_id], "seq": 1,
        "url": [f"https://shop.example.com/{MARKETS[m].language.split('-')[0]}?utm_source=line&utm_medium=line_message"
                f"&utm_campaign={m.lower()}-{c}-{th}" for m, c, th in zip(lc.market, lc.campaign_id, lc.theme)],
        "click": lc.clicks.astype(int), "unique_click": lc.unique_click.astype(int)})
    t["raw_line.followers_daily"] = res.line_daily.rename(columns={"market": "account"})
    friends = [i for i, lid in enumerate(cust.line_user_id) if lid is not None
               and cust.line_friend_day[i] <= (sc.end - sc.start).days]
    blocked_day = la[la.blocked].groupby("customer_id").campaign_id.min()
    send_by_campaign = camp.set_index("campaign_id").send_utc
    follow = []
    for i in friends:
        when = dt.datetime.combine(sc.start + dt.timedelta(days=int(cust.line_friend_day[i])), dt.time(12)) \
            + dt.timedelta(minutes=int(rng.integers(-600, 600)))
        follow.append((cust.line_user_id[i], cust.market[i], "follow", when))
        cid = cust.customer_id[i]
        if cid in blocked_day.index:
            follow.append((cust.line_user_id[i], cust.market[i], "unfollow",
                           send_by_campaign[blocked_day[cid]] + dt.timedelta(hours=float(rng.exponential(5)))))
    t["raw_line.webhook_events"] = pd.DataFrame(follow, columns=["user_id", "account", "type", "timestamp"]) \
        .sort_values("timestamp").reset_index(drop=True)
    t["raw_line.login_links"] = pd.DataFrame([(cust.line_user_id[i], int(cust.shop_customer_id[i]))
                                             for i in friends if cust.line_linked[i]],
                                            columns=["line_user_id", "shop_customer_id"])

    # ---- raw_crm ----
    t["raw_crm.campaign_plan"] = pd.DataFrame({
        "campaign_id": camp.campaign_id, "market": camp.market, "channel": camp.channel, "theme": camp.theme,
        "event_code": camp.event_code,
        "category": [list(CATEGORIES)[int(x)] if pd.notna(x) else None for x in camp.category],
        "segment": camp.segment, "name": camp.name, "send_at_local": camp.send_local, "send_at_utc": camp.send_utc,
        "email_campaign_id": [email_ids.get(c) for c in camp.campaign_id],
        "line_request_id": [req.get(c) for c in camp.campaign_id], "holdout_rate": sc.holdout_rate})
    h = a[a.is_holdout]
    line_ids = pd.Series(cust.line_user_id, index=cust.customer_id)
    t["raw_crm.holdouts"] = pd.DataFrame({
        "campaign_id": h.campaign_id.to_numpy(), "channel": h.channel.to_numpy(),
        "recipient": np.where(h.channel == "email", stored.reindex(h.customer_id).to_numpy(),
                              line_ids.reindex(h.customer_id).to_numpy())})

    # ---- truth ----
    t["truth.customers"] = pd.DataFrame({
        "customer_id": cust.customer_id, "market": cust.market, "shop_customer_id": cust.shop_customer_id,
        "email_contact_id": pd.Series(cust.email_contact_id, dtype="Int64").where(has_contact),
        "line_user_id": cust.line_user_id,
        "engagement": cust.engagement.round(4), "propensity": cust.propensity.round(4),
        "lifetime_end_date": [sc.start + dt.timedelta(days=int(x)) for x in cust.lifetime_end_day],
        "favourite_category": [list(CATEGORIES)[i] for i in cust.favourite_category],
        "apple_mail": cust.apple_mail, "bad_email": cust.bad_email, "line_linked": cust.line_linked})
    t["truth.audience"] = res.audience
    t["truth.orders"] = res.truth_orders
    t["truth.demand"] = res.demand
    t["truth.parameters"] = pd.DataFrame({"scenario": [sc.name],
                                          "parameters_json": [json.dumps(res.parameters, default=str, ensure_ascii=False)]})
    return t


def write(res: Result, path: str | Path) -> dict[str, int]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    counts = {}
    con = duckdb.connect(str(path))
    try:
        for name, df in tables(res).items():
            schema, table = name.split(".")
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            con.register("_df", df)
            con.execute(f"CREATE TABLE {schema}.{table} AS SELECT * FROM _df")
            con.unregister("_df")
            counts[name] = len(df)
    finally:
        con.close()
    return counts
