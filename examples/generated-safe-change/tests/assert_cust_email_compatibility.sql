-- Passing result: zero rows where phase-one values diverge.
select
    cust_email
from {{ ref('order_details__changesafe') }}
where cust_email is distinct from primary_email
