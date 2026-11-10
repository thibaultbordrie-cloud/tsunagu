# Loading the fictional world into Salesforce

`tsunagu generate --salesforce DIR` writes four CSV files shaped for Sales Cloud standard objects, ready for Data Loader or the Bulk API.

> **Status.** The files follow the public Salesforce object reference and are checked by tests (headers, links, sizes). They have **not been loaded into a live org yet**: that first run, in a free Developer Edition, is the next step. Expect to adjust details.

```bash
tsunagu generate --scenario tiny --out data/tiny.duckdb --salesforce data/salesforce
```

```text
salesforce/Contact                    300
salesforce/Campaign                    20
salesforce/CampaignMember           1,066
salesforce/Product2                    60
```

## What is written

| File | Object | Key | Content |
|---|---|---|---|
| `Product2.csv` | Product2 | `Tsunagu_Id__c` | the 60 products, `ProductCode` = SKU, `Family` = category |
| `Contact.csv` | Contact | `Tsunagu_Id__c` | one row per person, `HasOptedOutOfEmail` from the shop and the e-mail tool |
| `Campaign.csv` | Campaign | `Tsunagu_Id__c` | e-mail campaigns (`Type` = Email) and LINE broadcasts (`Type` = Other) |
| `CampaignMember.csv` | CampaignMember | none | who received which e-mail campaign: `Sent`, or `Responded` when they clicked |

Relationships use external IDs, not Salesforce record IDs: the columns `Campaign.Tsunagu_Id__c` and `Contact.Tsunagu_Id__c` tell the loader which records to link.

## Before loading

1. In Setup → Object Manager, add a custom field `Tsunagu_Id__c` (Text 40, **External ID**, **Unique**) on Contact, Campaign and Product2.
2. Load in this order: Product2, Contact and Campaign as **upsert** on `Tsunagu_Id__c`, then CampaignMember as **insert**.

## Choices worth knowing

- **Identity.** The e-mail tool stores some addresses with other case or stray spaces. Contacts are matched to shop customers on the trimmed, lower-cased address; subscribers the shop does not know become contacts of their own (`email-…` keys).
- **Volume.** A Developer Edition holds only a few megabytes. By default the export keeps 300 contacts (100 per market) and the last 4 campaigns per market and channel, about 1,500 records. `salesforce.write(res, folder, contacts=0, campaigns_per_market=0)` exports everything.
- **LINE has no members.** LINE reports aggregates only, so LINE campaigns are loaded without campaign members. This is the real limit of the channel, not a gap in the export.
- **Member statuses.** Only `Sent` and `Responded` are used: they are the two statuses a new campaign has by default.
- **Contacts have no account.** They load as private contacts. Attach them to an Account (or use Person Accounts) if other users must see them.
- **Country.** `MailingCountry` holds France, Japan or Taiwan as text. If State and Country/Territory Picklists are enabled in the org, the values must match its picklist.
- **Left out.** Orders: a standard Order needs an Account and a price book entry per product. The answer key (`truth` schema) is never exported.
