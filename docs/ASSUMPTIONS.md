# Assumptions

Everything below is a modelling choice made to produce a **plausible** world. None of it is measured market data, and none of it comes from a real company. The source of truth is [`src/tsunagu/config.py`](../src/tsunagu/config.py); a test checks that every parameter there is listed here.

Values are given as FR / JP / TW when they differ by market.

## People and consent

| Parameter | Value | Why |
|---|---|---|
| `customers` | 9,000 / 7,000 / 6,000 | Big enough for stable rates, small enough to build in ~20 s. |
| `signed_up_before_start` | 0.6 | Most customers already exist on day one; the rest sign up over time, more during sales. |
| `email_opt_in` | 0.82 / 0.55 / 0.45 | E-mail is the main CRM channel in France and a secondary one in Japan and Taiwan. |
| `line_friend` | 0 / 0.62 / 0.78 | LINE is the main messaging app in Japan and Taiwan; not used in France. |
| `line_login_linked` | 0.70 | Share of LINE friends who connected their shop account with LINE Login; the rest stay anonymous. |
| `bad_email` | 1.2 % | Addresses that hard-bounce on first send. |
| `email_typo_variant` | 2 % | Contacts stored in the e-mail tool with another case or stray spaces, to make identity matching real. |
| `apple_mail` | 0.45 / 0.62 / 0.48 | Share of readers on Apple Mail, higher in Japan where iPhone dominates. |

## E-mail

| Parameter | Value | Why |
|---|---|---|
| `email_open` | 0.22 / 0.16 / 0.14 | Human open probability for an average reader, before fatigue. |
| `email_click_to_open` | 0.12 / 0.10 / 0.09 | Click probability once a human opened. |
| `mpp_machine_open` | 0.92 | Apple Mail Privacy Protection pre-fetches almost every message: an "open" with no human behind it. |
| `soft_bounce` | 0.6 % | Temporary delivery failures. |
| `unsubscribe` | 0.06 % | Per delivered message, before fatigue; ×1.5 when the message was not opened. |
| `complaint` | 0.008 % | Spam reports; the address is then never e-mailed again. |

## LINE

| Parameter | Value | Why |
|---|---|---|
| `line_impression` | – / 0.68 / 0.62 | LINE messages are read far more than e-mail. |
| `line_click_to_impression` | – / 0.07 / 0.08 | Click once seen. |
| `line_block` | 0.09 % | Per delivered message, before fatigue; ×1.3 when the message was not read. LINE gives no per-user data, only aggregates. |

## Fatigue and creative

| Parameter | Value | Why |
|---|---|---|
| `open_decay_per_extra_message_7d` | 0.85 | Each extra message received in the last 7 days lowers the open probability by 15 %. |
| `optout_free_messages_30d` | e-mail 6, LINE 8 | Messages per 30 days a person tolerates before opt-outs grow. |
| `optout_growth_per_extra_message_30d` | e-mail 0.25, LINE 0.3 | Growth of opt-out probability per message above that. |
| `theme_effect` | e.g. event ×1.15 open, ×1.3 click | Event messages work better, teasers get fewer clicks, win-back gets fewer opens. |
| `favourite_category_click_boost` | 1.3 | People click more on their favourite category. |

## Purchases and the true effect of campaigns

| Parameter | Value | Why |
|---|---|---|
| `daily_order_rate` | 0.0030 / 0.0027 / 0.0031 | About one order a year for an average active customer, before calendar effects. |
| `mean_lifetime_days` | 540 | After it, a customer becomes mostly inactive (churn). |
| `churned_activity` | 0.1 | What is left of buying and engagement after churn. |
| `propensity_follows_engagement` | 0.7 | Engaged readers also buy more. This is what makes last-click attribution misleading. |
| `incremental_after_click` | 0.025 / 0.03 / 0.035 | **True** extra purchase probability over the effect window after a click. |
| `incremental_after_delivery` | 0.0002 | True effect of a message seen but not clicked. |
| `event_campaign_effect` | 1.4 | Event launches and last calls are stronger. |
| `effect_window_days` | 3 | How long a message keeps an effect. |
| `holdout_rate` | 5 % | Share of each audience held out. Deliberately realistic, so small effects are sometimes not detectable. |
| `utm_capture` | 0.85 | Clicks whose UTM survives to the order (app switches, other devices lose it). |
| `intent_click` | 0.35 | Buyers who would have bought anyway and use the last message they opened as a shortcut: a click, a UTM, no causal effect. |

## Baskets

| Parameter | Value | Why |
|---|---|---|
| `extra_items_mean` | 0.6 | Items beyond the first follow a Poisson law. |
| `double_quantity` | 10 % | Lines with quantity 2. |
| `event_discount` | 15 % / 10 % / 12 % | Discount when an event code is used. |
| `refunded`, `partially_refunded` | 2 %, 1 % | Order financial status. |

## Fixed parts of the world

- **Exchange rates** (fixed): 1 EUR = 160 JPY = 35 TWD. Cross-border price premium: ×1.15 Japan, ×1.10 Taiwan.
- **Price endings**: ¥…980, NT$…90, …,90 €.
- **Calendar uplifts**: one number per event (e.g. 雙11 ×2.2, 年貨採買 ×1.6, お盆 ×0.85), in [`events.py`](../src/tsunagu/events.py) and in the `ref.calendar_events` table. French sales dates follow the official rule; Mother's Day in France ignores the Pentecost exception.
- **Weekday and month shapes** of demand, and **hour-of-day** profiles of orders, in `events.py` and `simulate.py`.
- **Cadence**: weekly newsletters per market and channel, product drops, monthly win-back e-mail, and teaser / launch / last call around big events (`campaigns.py`).

## Scenario identity

`name`, `seed`, `start`, `end` identify a run. Same scenario, same seed, same world (tested).
