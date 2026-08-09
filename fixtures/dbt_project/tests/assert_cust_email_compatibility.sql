-- Passing result: zero rows where phase-one values diverge.
select
    cust_email
from {{ ref('order_details') }}
where cust_email is distinct from primary_email
