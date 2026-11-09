"""Write the same data as API responses, shaped after the public docs of each tool.

The goal is to let a future connector be written and tested offline: the field names and
nesting follow Brevo (email campaigns, contact lists), LINE Messaging API (message insight,
followers) and Shopify Admin REST (orders). The shapes are simplified; check the real API
reference before relying on any field in production.
"""
from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from ..simulate import Result
from ..universe import MARKETS
from .duckdb_out import tables


def _iso_z(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _money(x: float, currency: str) -> str:
    return f"{x:.0f}" if currency in ("JPY", "TWD") else f"{x:.2f}"


def write(res: Result, folder: str | Path) -> dict[str, int]:
    folder = Path(folder)
    t = tables(res)
    out: dict[str, int] = {}

    # Brevo: GET /v3/emailCampaigns (pages of 50) and GET /v3/contacts/lists
    camps = t["raw_email.campaigns"].sort_values("id")
    pages = [camps.iloc[i:i + 50] for i in range(0, len(camps), 50)]
    (folder / "brevo").mkdir(parents=True, exist_ok=True)
    for n, page in enumerate(pages, start=1):
        body = {"count": len(camps), "campaigns": [{
            "id": int(r.id), "name": r.name, "subject": r.subject, "type": "classic", "tag": r.tag,
            "status": "sent", "createdAt": _iso_z(r.sent_at - pd.Timedelta(days=2)), "sentDate": _iso_z(r.sent_at),
            "recipients": {"lists": [int(r.list_id)]},
            "statistics": {"globalStats": {
                "sent": int(r.sent), "delivered": int(r.delivered), "uniqueViews": int(r.unique_views),
                "trackableViews": int(r.trackable_views), "appleMppOpens": int(r.apple_mpp_opens),
                "uniqueClicks": int(r.unique_clicks), "clickers": int(r.clickers),
                "unsubscriptions": int(r.unsubscriptions), "hardBounces": int(r.hard_bounces),
                "softBounces": int(r.soft_bounces), "complaints": int(r.complaints)}}}
            for r in page.itertuples()]}
        (folder / "brevo" / f"emailCampaigns_page{n:03d}.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
    out["brevo/emailCampaigns"] = len(camps)
    last = t["raw_email.list_daily"].sort_values("date").groupby("list_id").tail(1)
    lists = t["raw_email.lists"].merge(last, left_on="id", right_on="list_id")
    body = {"count": len(lists), "lists": [{
        "id": int(r.id), "name": r.name, "folderId": 1, "totalSubscribers": int(r.subscribers),
        "uniqueSubscribers": int(r.subscribers - r.blacklisted), "totalBlacklisted": int(r.blacklisted)}
        for r in lists.itertuples()]}
    (folder / "brevo" / "contacts_lists.json").write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")

    # LINE: GET /v2/bot/insight/message/event?requestId=... and /v2/bot/insight/followers?date=yyyyMMdd
    ins = t["raw_line.message_insights"].merge(t["raw_line.message_clicks"], on="request_id")
    for account in ("JP", "TW"):
        d = folder / "line" / account
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "insight_message_event.jsonl", "w", encoding="utf-8") as f:
            for r in ins[ins.account == account].itertuples():
                f.write(json.dumps({"requestId": r.request_id, "response": {
                    "overview": {"requestId": r.request_id, "timestamp": int(pd.Timestamp(r.sent_at).timestamp()),
                                 "delivered": int(r.delivered), "uniqueImpression": int(r.unique_impression),
                                 "uniqueClick": int(r.unique_click_x), "uniqueMediaPlayed": None,
                                 "uniqueMediaPlayed100Percent": None},
                    "messages": [{"seq": 1, "impression": int(r.unique_impression), "mediaPlayed": None}],
                    "clicks": [{"seq": 1, "url": r.url, "click": int(r.click), "uniqueClick": int(r.unique_click_y),
                                "uniqueClickOfRequest": int(r.unique_click_y)}]}}, ensure_ascii=False) + "\n")
        fol = t["raw_line.followers_daily"]
        with open(d / "insight_followers.jsonl", "w", encoding="utf-8") as f:
            for r in fol[fol.account == account].itertuples():
                f.write(json.dumps({"date": pd.Timestamp(r.date).strftime("%Y%m%d"), "response": {
                    "status": "ready", "followers": int(r.followers), "targetedReaches": int(r.targeted_reaches),
                    "blocks": int(r.blocks)}}) + "\n")
        out[f"line/{account}/insight_message_event"] = int((ins.account == account).sum())

    # Shopify: GET /admin/api/.../orders.json, one order per line
    orders = t["raw_shop.orders"]
    items = t["raw_shop.order_line_items"].merge(t["ref.products"][["product_id", "name_fr", "name_ja", "name_zh_hant"]],
                                                 on="product_id")
    items_by_order = {k: g for k, g in items.groupby("order_id")}
    (folder / "shopify").mkdir(parents=True, exist_ok=True)
    title_col = {"fr": "name_fr", "ja": "name_ja", "zh-Hant": "name_zh_hant"}
    with open(folder / "shopify" / "orders.jsonl", "w", encoding="utf-8") as f:
        for r in orders.itertuples():
            mk = MARKETS[r.country_code]
            local = pd.Timestamp(r.created_at_local).to_pydatetime().replace(tzinfo=ZoneInfo(mk.timezone))
            g = items_by_order[r.id]
            f.write(json.dumps({
                "id": int(r.id), "name": r.name, "email": r.email, "created_at": local.isoformat(),
                "currency": r.currency, "subtotal_price": _money(r.subtotal_price, r.currency),
                "total_discounts": _money(r.total_discounts, r.currency),
                "total_price": _money(r.total_price, r.currency), "financial_status": r.financial_status,
                "source_name": "web", "landing_site": r.landing_site,
                "referring_site": r.referring_site if isinstance(r.referring_site, str) else None,
                "customer": {"id": int(r.customer_id)},
                "discount_codes": [{"code": r.discount_code, "amount": _money(r.total_discounts, r.currency),
                                    "type": "percentage"}] if isinstance(r.discount_code, str) else [],
                "shipping_lines": [{"price": _money(r.shipping_price, r.currency)}],
                "line_items": [{"id": int(r.id) * 100 + int(li.line_no), "product_id": int(li.product_id),
                                "sku": li.sku, "title": getattr(li, title_col[mk.language]),
                                "quantity": int(li.quantity), "price": _money(li.price, r.currency)}
                               for li in g.itertuples()],
            }, ensure_ascii=False) + "\n")
    out["shopify/orders"] = len(orders)
    (folder / "README.md").write_text(
        "# API-shaped samples (fictional)\n\nGenerated by `tsunagu generate --api`. Shapes follow the public "
        "docs of Brevo, LINE Messaging API and Shopify Admin REST, simplified. All data is fictional.\n",
        encoding="utf-8")
    return out
