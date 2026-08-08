# ChangeSafe rollback

Revert the generated model, schema, and compatibility test together, then run dbt parse before reopening downstream traffic.

1. Revert `models/marts/dim_customers.sql`.
2. Revert `models/marts/dim_customers.yml`.
3. Remove `tests/assert_customer_email_compatibility.sql`.
4. Confirm `customer_email` remains available to every downstream consumer.
5. Run `dbt parse` and the project test suite before republishing.
