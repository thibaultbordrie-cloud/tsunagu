-- 3. The answer key: orders truly caused by e-mail, per send
with caused as (
  select p.market, count(*) as orders
  from truth.orders t join raw_crm.campaign_plan p on p.campaign_id = t.causing_campaign_id
  where p.channel = 'email' group by 1),
sends as (
  select p.market, count(*) as n from truth.audience a join raw_crm.campaign_plan p using (campaign_id)
  where p.channel = 'email' and a.delivered group by 1)
select market, round(100.0 * orders / n, 3) as true_uplift_pts from caused join sends using (market) order by 1
