-- 2. What the holdout groups say, e-mail only, from raw data: 3-day conversion
with sends as (
  select p.campaign_id, p.market, p.send_at_utc, lower(trim(e.email)) as email, false as holdout
  from raw_crm.campaign_plan p
  join raw_email.events e on e.campaign_id = p.email_campaign_id and e.event = 'delivered'
  union all
  select p.campaign_id, p.market, p.send_at_utc, lower(trim(h.recipient)), true
  from raw_crm.campaign_plan p join raw_crm.holdouts h using (campaign_id)
  where p.channel = 'email'),
conv as (
  select s.market, s.holdout,
         exists (select 1 from raw_shop.orders o where o.email = s.email
                 and o.created_at between s.send_at_utc and s.send_at_utc + interval 3 day) as bought
  from sends s),
rates as (
  select market, holdout, count(*) as n, avg(bought::int) as p from conv group by all)
select r.market,
       round(100 * r.p, 3) as recipients_pct, round(100 * h.p, 3) as holdout_pct,
       round(100 * (r.p - h.p), 3) as uplift_pts,
       round(100 * (r.p - h.p - 1.96 * sqrt(r.p * (1 - r.p) / r.n + h.p * (1 - h.p) / h.n)), 3) as ci_low,
       round(100 * (r.p - h.p + 1.96 * sqrt(r.p * (1 - r.p) / r.n + h.p * (1 - h.p) / h.n)), 3) as ci_high,
       h.n as holdout_sends
from rates r join rates h on h.market = r.market and h.holdout and not r.holdout
order by 1
