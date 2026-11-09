import json

from tsunagu.__main__ import main

BREVO_STATS = {"sent", "delivered", "uniqueViews", "trackableViews", "appleMppOpens", "uniqueClicks", "clickers",
               "unsubscriptions", "hardBounces", "softBounces", "complaints"}


def test_brevo_campaign_pages(tiny_api):
    pages = sorted((tiny_api / "brevo").glob("emailCampaigns_page*.json"))
    assert pages
    body = json.loads(pages[0].read_text(encoding="utf-8"))
    assert set(body) == {"count", "campaigns"} and len(body["campaigns"]) <= 50
    c = body["campaigns"][0]
    assert set(c["statistics"]["globalStats"]) == BREVO_STATS
    assert c["sentDate"].endswith(".000Z")


def test_line_insight_shape(tiny_api):
    path = tiny_api / "line" / "JP" / "insight_message_event.jsonl"
    first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    overview = first["response"]["overview"]
    assert {"requestId", "timestamp", "delivered", "uniqueImpression", "uniqueClick"} <= set(overview)
    assert overview["uniqueClick"] <= overview["uniqueImpression"] <= overview["delivered"]
    follower = json.loads((tiny_api / "line" / "TW" / "insight_followers.jsonl").read_text().splitlines()[-1])
    assert follower["response"]["status"] == "ready" and len(follower["date"]) == 8


def test_shopify_orders_use_local_time_and_string_money(tiny_api):
    for line in (tiny_api / "shopify" / "orders.jsonl").read_text(encoding="utf-8").splitlines()[:200]:
        o = json.loads(line)
        assert o["created_at"][-6:] in ("+09:00", "+08:00", "+01:00", "+02:00")
        assert isinstance(o["total_price"], str) and o["line_items"]
        if o["currency"] in ("JPY", "TWD"):
            assert "." not in o["total_price"]


def test_cli_generate_validate_describe(tmp_path, capsys):
    db = tmp_path / "w.duckdb"
    assert main(["generate", "--scenario", "tiny", "--out", str(db)]) == 0
    assert main(["validate", str(db)]) == 0
    assert main(["describe", str(db)]) == 0
    out = capsys.readouterr().out
    assert "Contract: OK" in out and "truly caused" in out


def test_set_overrides_one_parameter(tmp_path, capsys):
    db = tmp_path / "half.duckdb"
    assert main(["generate", "--scenario", "tiny", "--out", str(db), "--set", "holdout_rate=0.5",
                 "--set", 'line_friend={"TW": 0.9}']) == 0
    out = capsys.readouterr().out
    assert "override holdout_rate = 0.5" in out and "'TW': 0.9" in out


def test_set_refuses_unknown_or_wrong_values():
    import pytest

    from tsunagu.__main__ import parse_overrides
    from tsunagu.config import SCENARIOS

    base = SCENARIOS["tiny"]
    for bad in (["nope=1"], ["holdout_rate=abc"], ['holdout_rate="x"'], ['email_open={"US": 0.1}']):
        with pytest.raises(SystemExit):
            parse_overrides(bad, base)


def test_example_queries_run(tiny_db, capsys):
    from pathlib import Path

    for sql in sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.sql")):
        assert main(["query", str(tiny_db), str(sql)]) == 0
    assert "uplift" in capsys.readouterr().out
