# ChangeSafe rollback

Rollback phase one by reverting the addition or exposure of primary_email while retaining customer_email. Because phase one keeps the old field, existing consumers can continue using customer_email during rollback. Do not remove customer_email as part of this phase.

1. Revert `models/marts/dim_customers.sql`.
2. Revert `models/marts/dim_customers.yml`.
3. Remove `tests/assert_customer_email_compatibility.sql`.
4. Confirm `customer_email` remains available to every downstream consumer.
5. Run `dbt parse` and the project test suite before republishing.
