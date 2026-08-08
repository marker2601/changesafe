-- Passing result: zero rows where phase-one values diverge.
select
    customer_id
from {{ ref('dim_customers') }}
where customer_email is distinct from primary_email
