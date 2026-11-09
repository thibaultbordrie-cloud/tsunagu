"""The generated world must be reproducible, consistent, and show the behaviours it promises."""
import hashlib
import shutil

import duckdb
import pandas as pd
import pytest

from tsunagu.config import SCENARIOS
from tsunagu.contract import validate
from tsunagu.simulate import run


def _fingerprint(res) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(res.orders, index=False).values.tobytes()).hexdigest()


def q(db, sql):
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_same_seed_same_world(tiny):
    assert _fingerprint(run(SCENARIOS["tiny"])) == _fingerprint(tiny)


def test_other_seed_other_world(tiny):
    assert _fingerprint(run(SCENARIOS["tiny"].with_(seed=8))) != _fingerprint(tiny)


def test_contract_holds(tiny_db):
    assert validate(tiny_db) == []


def test_contract_catches_a_broken_total(tiny_db, tmp_path):
    broken = tmp_path / "broken.duckdb"
    shutil.copy(tiny_db, broken)
    con = duckdb.connect(str(broken))
    con.execute("update raw_shop.orders set total_price = total_price + 5 where id = 1")
    con.close()
    rules = [b.rule for b in validate(broken)]
    assert any("total_price" in r for r in rules)


def test_line_is_opened_more_than_email_in_asia(tiny_db):
    rows = dict(q(tiny_db, """
        select l.market, sum(c.trackable_views) / sum(c.delivered) from raw_email.campaigns c
        join raw_email.lists l on l.id = c.list_id group by 1"""))
    line = dict(q(tiny_db, """select account, sum(unique_impression) / sum(delivered)
                              from raw_line.message_insights group by 1"""))
    assert line["JP"] > 2 * rows["JP"] and line["TW"] > 2 * rows["TW"]


def test_apple_mpp_inflates_email_opens(tiny_db):
    views, trackable = q(tiny_db, "select sum(unique_views), sum(trackable_views) from raw_email.campaigns")[0]
    assert views > 2 * trackable


def test_campaign_effect_only_reaches_recipients(tiny_db):
    """No order is ever caused by a campaign the customer was held out of."""
    bad = q(tiny_db, """
        select count(*) from truth.orders t join truth.audience a
          on a.campaign_id = t.causing_campaign_id and a.customer_id = t.customer_id
        where a.is_holdout""")[0][0]
    assert bad == 0


def test_holdout_comparison_recovers_a_strong_effect():
    """With a big effect and half the audience held out, recipients clearly convert more."""
    sc = SCENARIOS["tiny"].with_(holdout_rate=0.5, incremental_after_click={"FR": 0.4, "JP": 0.4, "TW": 0.4},
                                 incremental_after_delivery=0.01)
    res = run(sc)
    send = {c.campaign_id: c.send_utc for c in res.campaigns}
    orders = res.orders.merge(res.truth_orders[["order_id", "customer_id"]], on="order_id")
    times = orders.groupby("customer_id").created_at_utc.apply(list).to_dict()
    a = res.audience
    conv = [any(send[c] <= t <= send[c] + pd.Timedelta(days=3) for t in times.get(cu, []))
            for c, cu in zip(a.campaign_id, a.customer_id)]
    rate = pd.Series(conv).groupby(a.is_holdout.to_numpy()).mean()
    assert rate[False] > 1.3 * rate[True]


def test_last_click_overstates_what_campaigns_cause(tiny_db):
    utm, caused = q(tiny_db, """
        select avg((o.landing_site like '%utm_campaign=%')::int), avg((t.cause = 'campaign_incremental')::int)
        from raw_shop.orders o join truth.orders t on t.order_id = o.id""")[0]
    assert utm > caused


def test_double_11_is_the_taiwan_peak(tiny_db):
    by_day = dict(q(tiny_db, """select created_at_local::date, count(*) from raw_shop.orders
                                where country_code = 'TW' group by 1"""))
    double_11 = sum(n for d, n in by_day.items() if (d.month, d.day) in ((11, 10), (11, 11))) / 2
    median = sorted(by_day.values())[len(by_day) // 2]
    assert double_11 > 1.6 * median


def test_opted_out_people_are_never_messaged_again(tiny_db):
    late = q(tiny_db, """
        with out as (
          select a.customer_id, p.channel, min(p.send_at_utc) as t from truth.audience a
          join raw_crm.campaign_plan p using (campaign_id)
          where a.unsubscribed or a.complained or a.hard_bounce or a.blocked group by 1, 2)
        select count(*) from truth.audience a join raw_crm.campaign_plan p using (campaign_id)
        join out on out.customer_id = a.customer_id and out.channel = p.channel
        where p.send_at_utc > out.t""")[0][0]
    assert late == 0


def test_identity_is_messy_but_recoverable(tiny_db):
    differ, total, recovered = q(tiny_db, """
        select sum((c.email <> s.email)::int), count(*), sum((lower(trim(c.email)) = s.email)::int)
        from raw_email.contacts c
        join truth.customers t on t.email_contact_id = c.id
        join raw_shop.customers s on s.id = t.shop_customer_id""")[0]
    assert 0 < differ < 0.06 * total
    assert recovered == total


def test_only_some_line_friends_are_linked(tiny_db):
    linked, friends = q(tiny_db, """
        select (select count(*) from raw_line.login_links),
               (select count(distinct user_id) from raw_line.webhook_events where type = 'follow')""")[0]
    assert 0.6 < linked / friends < 0.8


@pytest.mark.parametrize("table", ["raw_shop.customers", "raw_email.contacts"])
def test_no_real_looking_contact_data(tiny_db, table):
    cols = [r[0] for r in q(tiny_db, f"select column_name from information_schema.columns "
                                     f"where table_schema || '.' || table_name = '{table}'")]
    assert not any("phone" in c or "birth" in c for c in cols)
    bad = q(tiny_db, f"select count(*) from {table} where not regexp_matches(lower(trim(email)), '@example\\.(com|org)$')")
    assert bad[0][0] == 0
