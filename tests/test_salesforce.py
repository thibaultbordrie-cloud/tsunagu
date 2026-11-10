"""The Sales Cloud export: right headers, links that resolve, small enough for a free org."""
import csv

import pytest

from tsunagu.exporters import salesforce


@pytest.fixture(scope="module")
def load(tiny, tmp_path_factory):
    folder = tmp_path_factory.mktemp("sf")
    counts = salesforce.write(tiny, folder)
    rows = {name: list(csv.DictReader(open(folder / f"{name}.csv", encoding="utf-8"))) for name in salesforce.HEADERS}
    return counts, rows


def test_headers_are_api_field_names(load):
    _, rows = load
    for name, header in salesforce.HEADERS.items():
        assert list(rows[name][0].keys()) == header


def test_every_member_points_to_an_exported_campaign_and_contact(load):
    _, rows = load
    campaigns = {r["Tsunagu_Id__c"] for r in rows["Campaign"]}
    contacts = {r["Tsunagu_Id__c"] for r in rows["Contact"]}
    assert rows["CampaignMember"]
    for m in rows["CampaignMember"]:
        assert m["Campaign.Tsunagu_Id__c"] in campaigns
        assert m["Contact.Tsunagu_Id__c"] in contacts
        assert m["Status"] in ("Sent", "Responded")
    pairs = [(m["Campaign.Tsunagu_Id__c"], m["Contact.Tsunagu_Id__c"]) for m in rows["CampaignMember"]]
    assert len(pairs) == len(set(pairs)), "a contact is a member of a campaign only once"


def test_external_ids_are_unique_and_required_fields_are_filled(load):
    _, rows = load
    for name in ("Contact", "Campaign", "Product2"):
        ids = [r["Tsunagu_Id__c"] for r in rows[name]]
        assert len(ids) == len(set(ids))
    assert all(r["LastName"] for r in rows["Contact"])
    assert all(0 < len(r["Name"]) <= 80 for r in rows["Campaign"])
    assert all(r["HasOptedOutOfEmail"] in ("true", "false") for r in rows["Contact"])


def test_identity_is_resolved_on_the_normalised_address(load):
    _, rows = load
    emails = [r["Email"] for r in rows["Contact"]]
    assert all(e == e.strip().lower() for e in emails)
    assert len(emails) == len(set(emails))
    assert all(e.endswith(("@example.com", "@example.org")) for e in emails)


def test_default_sample_fits_a_free_org(load):
    counts, rows = load
    assert counts["Contact"] <= 300
    assert sum(counts.values()) < 2500
    assert {r["Type"] for r in rows["Campaign"]} == {"Email", "Other"}
    line = [r for r in rows["Campaign"] if r["Type"] == "Other"]
    members_of = {m["Campaign.Tsunagu_Id__c"] for m in rows["CampaignMember"]}
    assert line and not members_of.intersection(r["Tsunagu_Id__c"] for r in line), "LINE gives no per-user data"


def test_no_limit_exports_everyone(tiny, tmp_path):
    counts = salesforce.write(tiny, tmp_path, contacts=0, campaigns_per_market=0)
    assert counts["Contact"] > 1000 and counts["Campaign"] > 100


def test_clickers_are_marked_as_responded(tiny, tmp_path):
    salesforce.write(tiny, tmp_path, contacts=0, campaigns_per_market=0)
    statuses = [r["Status"] for r in csv.DictReader(open(tmp_path / "CampaignMember.csv", encoding="utf-8"))]
    assert 0 < statuses.count("Responded") < 0.1 * len(statuses)
