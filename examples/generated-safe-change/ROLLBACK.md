# ChangeSafe rollback

Revert the generated compatibility layer, schema, and test together, then run dbt parse before reopening downstream traffic.

1. Move downstream consumers from `order_details__changesafe` back to `order_details` before removing generated artifacts.
2. Confirm `cust_email` remains available to every downstream consumer.
3. Revert `models/marts/order_details__changesafe.sql`.
4. Revert `models/marts/order_details__changesafe.yml`.
5. Remove `tests/assert_cust_email_compatibility.sql`.
6. Run `dbt parse` and the project test suite before republishing.
