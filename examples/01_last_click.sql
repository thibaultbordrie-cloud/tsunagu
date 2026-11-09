-- 1. What last-click attribution says (shop data only)
select country_code as market,
       coalesce(nullif(regexp_extract(landing_site, 'utm_source=([a-z]+)', 1), ''), 'no campaign') as source,
       count(*) as orders,
       round(100.0 * count(*) / sum(count(*)) over (partition by country_code), 1) as pct_orders
from raw_shop.orders
group by 1, 2 order by market, orders desc
