# Worked example: did the e-mails really sell anything?

Three queries on the standard world (`tsunagu generate --scenario standard`). Each one is a file in [`examples/`](../examples) that you can run with:

```bash
tsunagu query data/tsunagu.duckdb examples/02_holdout_email_uplift.sql
```

## 1. What last-click attribution says

[`01_last_click.sql`](../examples/01_last_click.sql) reads only the shop data: the UTM of the landing page.

```text
market  source       orders  pct_orders
FR      no campaign    7116        90.4
FR      email           755         9.6
JP      no campaign    4523        83.7
JP      line            722        13.4
JP      email           161         3.0
TW      no campaign    4612        78.9
TW      line           1165        19.9
TW      email            68         1.2
```

In Taiwan, a team reading this would say LINE drives one order in five.

## 2. What the holdout groups say

[`02_holdout_email_uplift.sql`](../examples/02_holdout_email_uplift.sql) uses only raw data: who received each e-mail (the e-mail tool's `delivered` events), who was held out (`raw_crm.holdouts`), and who bought within 3 days (the shop, joined on the normalised e-mail address). It compares the two groups with a 95 % confidence interval on the difference.

With the default 5 % holdout:

```text
market  recipients_pct  holdout_pct  uplift_pts  ci_low  ci_high  holdout_sends
FR               0.529        0.487       0.042  -0.022    0.106          48097
JP               0.458        0.511      -0.053  -0.156    0.049          19568
TW               0.627        0.783      -0.156  -0.373    0.060           6640
```

Every interval contains zero: **the test cannot tell**. Not because e-mail does nothing, but because a 5 % holdout is too small for an effect this size.

## 3. The answer key

[`03_answer_key_email_uplift.sql`](../examples/03_answer_key_email_uplift.sql) reads the `truth` schema, which a real team never has:

```text
market  true_uplift_pts
FR                0.054
JP                0.041
TW                0.041
```

E-mail does work, about +0.05 point of 3-day conversion per message sent: one extra order for roughly every 2,000 e-mails.

## 4. The same question with a bigger holdout

```bash
tsunagu generate --scenario standard --set holdout_rate=0.2 --out data/h20.duckdb
```

```text
market  recipients_pct  holdout_pct  uplift_pts  ci_low  ci_high  holdout_sends      true
FR               0.515        0.470       0.045   0.011    0.079         197825     0.060
JP               0.478        0.399       0.080   0.030    0.130          79023     0.042
TW               0.557        0.589      -0.032  -0.134    0.070          26811     0.033
```

France and Japan are now measured, and the true value falls inside both intervals. Taiwan still cannot be measured: it sends too few e-mails. Its CRM runs on LINE.

A back-of-the-envelope power calculation gives the same answer. To detect +0.05 point on a 0.5 % base rate (80 % power, 5 % risk) with France's volume of about 960,000 e-mails in 22 months, the holdout has to be around **20 %** of each audience.

## What to take away

- Last-click is not a measure of effect: in this world, fewer than half the orders it credits to a campaign were caused by it.
- A holdout only answers if it is big enough for the effect you expect. Size it before the campaign, not after.
- Because Tsunagu keeps the answer key, a new attribution method, a dbt model or an AI agent can be **scored**, not just demonstrated.
