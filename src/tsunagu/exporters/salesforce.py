"""Write a small Sales Cloud load: CSV files for Contact, Campaign, CampaignMember and Product2.

The files follow the Salesforce object reference and the Data Loader / Bulk API conventions:
one CSV per object, UTF-8, API field names as headers, and relationships resolved through an
external ID (`Campaign.Tsunagu_Id__c`, `Contact.Tsunagu_Id__c`) instead of Salesforce record IDs.

Two things a real integration has to deal with are done here on purpose:

* identity: the e-mail tool stores some addresses with other case or stray spaces, so contacts
  are matched to shop customers on the trimmed, lower-cased address;
* volume: a free Developer Edition holds only a few megabytes, so the export keeps a sample
  (300 contacts and the last 4 e-mail campaigns of each market by default).

LINE campaigns are exported as campaigns without members: LINE gives no per-user statistics.
Orders are left out of this first version (a standard Order needs an Account and a price book).
These files have not been loaded into a live org yet; see docs/SALESFORCE.md.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from ..simulate import Result
from ..universe import MARKETS
from .duckdb_out import EMAIL_LIST_ID, tables

EXTERNAL_ID = "Tsunagu_Id__c"
COUNTRY = {"FR": "France", "JP": "Japan", "TW": "Taiwan"}
HEADERS = {
    "Contact": [EXTERNAL_ID, "FirstName", "LastName", "Email", "MailingCountry", "HasOptedOutOfEmail",
                "LeadSource", "Description"],
    "Campaign": [EXTERNAL_ID, "Name", "Type", "Status", "IsActive", "StartDate", "EndDate", "NumberSent",
                 "Description"],
    "CampaignMember": [f"Campaign.{EXTERNAL_ID}", f"Contact.{EXTERNAL_ID}", "Status"],
    "Product2": [EXTERNAL_ID, "Name", "ProductCode", "Family", "IsActive", "Description"],
}


def _norm(email: str) -> str:
    return str(email).strip().lower()


def _bool(x) -> str:
    return "true" if bool(x) else "false"


def _contacts(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per person: shop customers, plus e-mail contacts the shop does not know."""
    shop = t["raw_shop.customers"].copy()
    shop["key"] = shop["email"].map(_norm)
    mail = t["raw_email.contacts"].copy()
    mail["key"] = mail["email"].map(_norm)
    opted_out = dict(zip(mail["key"], mail["email_blacklisted"], strict=True))
    rows = []
    for r in shop.itertuples():
        rows.append({
            "key": r.key, "market": r.country_code, EXTERNAL_ID: f"shop-{r.id}",
            "FirstName": r.first_name, "LastName": r.last_name, "Email": r.key,
            "HasOptedOutOfEmail": _bool((not r.accepts_marketing) or opted_out.get(r.key, False)),
            "Description": f"Shop customer since {pd.Timestamp(r.created_at).date()}"})
    known = set(shop["key"])
    for r in mail[~mail["key"].isin(known)].itertuples():
        rows.append({
            "key": r.key, "market": r.country, EXTERNAL_ID: f"email-{r.id}",
            "FirstName": r.firstname, "LastName": r.lastname, "Email": r.key,
            "HasOptedOutOfEmail": _bool(r.email_blacklisted),
            "Description": f"Newsletter subscriber since {pd.Timestamp(r.created_at).date()}"})
    out = pd.DataFrame(rows).drop_duplicates("key").sort_values(EXTERNAL_ID).reset_index(drop=True)
    out["MailingCountry"] = out["market"].map(COUNTRY)
    out["LeadSource"] = "Web"
    return out


def _campaigns(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    plan = t["raw_crm.campaign_plan"]
    sent = dict(zip(t["raw_email.campaigns"]["id"], t["raw_email.campaigns"]["sent"], strict=True))
    rows = []
    for r in plan.sort_values("send_at_utc").itertuples():
        email_id = None if pd.isna(r.email_campaign_id) else int(r.email_campaign_id)
        day = pd.Timestamp(r.send_at_local).date().isoformat()
        rows.append({
            "market": r.market, "channel": r.channel, "email_id": email_id,
            EXTERNAL_ID: f"plan-{int(r.campaign_id)}",
            "Name": f"{r.market} {r.channel} {day} {r.name}"[:80],
            "Type": "Email" if r.channel == "email" else "Other", "Status": "Completed", "IsActive": "false",
            "StartDate": day, "EndDate": day,
            "NumberSent": "" if email_id is None else int(sent.get(email_id, 0)),
            "Description": f"Theme: {r.theme}. Segment: {r.segment}. Channel: {r.channel}. Market: {r.market}."})
    return pd.DataFrame(rows)


def write(res: Result, folder: str | Path, contacts: int = 300, campaigns_per_market: int = 4) -> dict[str, int]:
    """Write the four CSV files. `contacts=0` or `campaigns_per_market=0` means no limit."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    t = tables(res)

    people = _contacts(t)
    camps = _campaigns(t)
    if campaigns_per_market:
        # Keep the latest e-mail campaigns of each market, and the latest LINE ones next to them.
        camps = camps.groupby(["market", "channel"], sort=False).tail(campaigns_per_market)
    list_market = {v: k for k, v in EMAIL_LIST_ID.items()}
    email_market = {int(c.id): list_market[int(c.list_id)] for c in t["raw_email.campaigns"].itertuples()}
    kept_email = {int(e): x for e, x in zip(camps["email_id"], camps[EXTERNAL_ID], strict=True) if pd.notna(e)}

    events = t["raw_email.events"]
    events = events[events["campaign_id"].isin(kept_email) & events["event"].isin(["delivered", "clicked"])].copy()
    events["key"] = events["email"].map(_norm)
    if contacts:
        # Sample the people who received the kept campaigns, the same number in each market.
        reached = events.drop_duplicates("key").assign(market=lambda d: d["campaign_id"].map(email_market))
        per_market = max(1, contacts // len(MARKETS))
        keep = set(reached.sort_values("key").groupby("market").head(per_market)["key"])
        people = people[people["key"].isin(keep)]
    ids = dict(zip(people["key"], people[EXTERNAL_ID], strict=True))
    events = events[events["key"].isin(ids)]
    clicked = set(zip(events.loc[events["event"] == "clicked", "campaign_id"],
                      events.loc[events["event"] == "clicked", "key"], strict=True))
    members = events[events["event"] == "delivered"].drop_duplicates(["campaign_id", "key"])
    member_rows = [{
        f"Campaign.{EXTERNAL_ID}": kept_email[int(m.campaign_id)], f"Contact.{EXTERNAL_ID}": ids[m.key],
        "Status": "Responded" if (m.campaign_id, m.key) in clicked else "Sent"}
        for m in members.sort_values(["campaign_id", "key"]).itertuples()]

    products = [{
        EXTERNAL_ID: f"product-{p.product_id}", "Name": p.name_fr[:255], "ProductCode": p.sku,
        "Family": p.category_en, "IsActive": "true", "Description": f"{p.name_ja} / {p.name_zh_hant}"}
        for p in t["ref.products"].itertuples()]

    data = {"Contact": people.to_dict("records"), "Campaign": camps.to_dict("records"),
            "CampaignMember": member_rows, "Product2": products}
    for name, rows in data.items():
        with open(folder / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADERS[name], extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    return {name: len(rows) for name, rows in data.items()}
