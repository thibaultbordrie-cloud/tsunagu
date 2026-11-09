"""A one-screen summary of a generated warehouse."""
from __future__ import annotations

from pathlib import Path

import duckdb

from .universe import FX_FROM_EUR


def _table(rows, headers) -> str:
    cells = [[str(h) for h in headers]] + [["-" if c is None else str(c) for c in r] for r in rows]
    width = [max(len(r[i]) for r in cells) for i in range(len(headers))]
    lines = ["  ".join(c.rjust(width[i]) if i else c.ljust(width[i]) for i, c in enumerate(r)) for r in cells]
    lines.insert(1, "  ".join("-" * w for w in width))
    return "\n".join(lines)


def describe(path: str | Path) -> str:
    con = duckdb.connect(str(path), read_only=True)
    fx = ", ".join(f"('{k}', {v})" for k, v in FX_FROM_EUR.items())
    out = []
    try:
        period = con.execute(
            "select min(created_at_local)::date, max(created_at_local)::date from raw_shop.orders").fetchone()
        out.append(f"Lune & Lin (fictional) · orders from {period[0]} to {period[1]}\n")
        rows = con.execute(f"""
            with fx(currency, rate) as (values {fx})
            select o.country_code, count(distinct c.id), count(*), round(sum(o.total_price / fx.rate))::bigint,
                   round(avg(o.total_price / fx.rate), 1), any_value(o.currency)
            from raw_shop.orders o join fx using (currency)
            join raw_shop.customers c on c.id = o.customer_id
            group by 1 order by 1""").fetchall()
        out.append(_table(rows, ["market", "buyers", "orders", "revenue EUR eq.", "avg basket EUR", "currency"]))
        rows = con.execute("""
            select l.market, 'email', sum(c.delivered),
                   round(100.0 * sum(c.unique_views) / sum(c.delivered), 1),
                   round(100.0 * sum(c.trackable_views) / sum(c.delivered), 1),
                   round(100.0 * sum(c.clickers) / sum(c.delivered), 2),
                   round(100.0 * sum(c.unsubscriptions) / sum(c.delivered), 3)
            from raw_email.campaigns c join raw_email.lists l on l.id = c.list_id group by 1
            union all
            select account, 'line', sum(delivered), round(100.0 * sum(unique_impression) / sum(delivered), 1),
                   round(100.0 * sum(unique_impression) / sum(delivered), 1),
                   round(100.0 * sum(unique_click) / sum(delivered), 2), null
            from raw_line.message_insights group by 1 order by 1, 2""").fetchall()
        out.append("\nMessages")
        out.append(_table(rows, ["market", "channel", "delivered", "open %", "open % w/o Apple MPP", "click %",
                                 "unsub %"]))
        blocks = con.execute("""select account, round(100.0 * blocks / followers, 1) from raw_line.followers_daily
                                qualify row_number() over (partition by account order by date desc) = 1
                                order by 1""").fetchall()
        out.append("LINE friends who blocked the account by the end: "
                   + ", ".join(f"{a} {b} %" for a, b in blocks))
        rows = con.execute("""
            select o.country_code,
                   round(100.0 * avg((o.landing_site like '%utm_campaign=%')::int), 1),
                   round(100.0 * avg((t.cause = 'campaign_incremental')::int), 1),
                   round(100.0 * avg((t.cause = 'campaign_incremental')::int)
                         filter (where o.landing_site like '%utm_campaign=%'), 1)
            from raw_shop.orders o join truth.orders t on t.order_id = o.id group by 1 order by 1""").fetchall()
        out.append("\nWhat last-click says vs what really happened (answer key from the truth schema)")
        out.append(_table(rows, ["market", "% orders with a campaign UTM", "% orders truly caused",
                                 "% of UTM orders truly caused"]))
    finally:
        con.close()
    return "\n".join(out)
