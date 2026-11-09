# Security and privacy

## What this repository contains

Code, tests and a generator of **fictional** data. No API key, no password, no real customer and no business figure. The generated warehouse is not committed (`data/` is ignored); anyone can rebuild it with `tsunagu generate`.

Tests enforce it:

- generated people only have `example.com` / `example.org` addresses, and no phone number or birth date column exists;
- `tests/test_anonymity.py` refuses identifying names (kept as hashes), non-example e-mail addresses and public IP addresses in every file;
- the brand, people, products and prices are invented; names come from the Faker library.

## Supply chain

- CI runs with a read-only token.
- Dependabot proposes grouped updates of actions and Python dependencies every week.

## Reporting a problem

If you find something sensitive here, please open a [private security advisory](../../security/advisories/new) rather than a public issue.
