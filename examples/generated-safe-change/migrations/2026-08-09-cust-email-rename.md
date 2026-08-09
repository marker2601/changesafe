# Migration: rename `cust_email` to `primary_email`

**Owner:** Ian Chen  
**Risk:** 85/100 — Critical  
**Deprecation window:** through 2026-09-08

## Phase one

The governed base model remains unchanged in phase one: `order_details`. ChangeSafe adds compatibility relation `order_details__changesafe`. Downstream owners must switch to `order_details__changesafe` and migrate to `primary_email`.

Keep `cust_email` and introduce `primary_email` during phase one. Update the dbt contract and enforce the operation-specific compatibility invariant.

`cust_email` remains available for a 30-day deprecation window and is removed only after every recorded downstream consumer migrates.

## Downstream evidence

- `Order Details` — Data Platform Team — `urn:li:dataset:(urn:li:dataPlatform:looker,b2fd91.order-entry.explore.order_details,PROD)`
- `ORDER_DETAILS` — Ecommerce Operations — `urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)`
- `order_details` — Data Platform Team — `urn:li:dataset:(urn:li:dataPlatform:looker,b2fd91.order-entry-looker.view.order_details,PROD)`
- `ORDER_DETAILS` — Unassigned — `urn:li:dataset:(urn:li:dataPlatform:powerbi,b2fd91.datahub_order_entries.ORDER_DETAILS,PROD)`
- `Customer Analytics Measures` — Unassigned — `urn:li:dataset:(urn:li:dataPlatform:powerbi,b2fd91.datahub_order_entries.Customer_Analytics_Measures,PROD)`
- `Essential KPI Measures` — Unassigned — `urn:li:dataset:(urn:li:dataPlatform:powerbi,b2fd91.datahub_order_entries.Essential_KPI_Measures,PROD)`
- `Geographic Measures` — Unassigned — `urn:li:dataset:(urn:li:dataPlatform:powerbi,b2fd91.datahub_order_entries.Geographic_Measures,PROD)`
- `Product Perfromance Measures` — Unassigned — `urn:li:dataset:(urn:li:dataPlatform:powerbi,b2fd91.datahub_order_entries.Product_Perfromance_Measures,PROD)`
- `Time Inteligence Measures` — Unassigned — `urn:li:dataset:(urn:li:dataPlatform:powerbi,b2fd91.datahub_order_entries.Time_Inteligence_Measures,PROD)`
- `ORDER_DETAILS_REPLICA` — Unassigned — `urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details_replica,PROD)`
- `Order Entry Dashboard` — Marketing — `urn:li:dashboard:(tableau,b2fd91.843bf583-900b-f1ba-0532-b5e67a0373dc)`
- `datahub_order_entries` — Unassigned — `urn:li:dashboard:(powerbi,b2fd91.reports.66666666-7777-8888-9999-000000000000)`
- `Orders By Month` — Unassigned — `urn:li:chart:(tableau,b2fd91.89f38fd7-058d-b66a-6db0-4f85f105468a)`
- `Popular Products Categories` — Unassigned — `urn:li:chart:(tableau,b2fd91.b8c660a8-10ea-e32a-b823-fa655e1c2f43)`
- `Promotions` — Unassigned — `urn:li:chart:(tableau,b2fd91.e051d978-989f-a329-5458-e01721b05570)`
- `Order Mode` — Unassigned — `urn:li:chart:(tableau,b2fd91.e36d7772-ac4d-4fd0-a893-aec88f3aa13e)`
- `Order Entry Dashboard` — Ecommerce Operations — `urn:li:dashboard:(looker,b2fd91.dashboards.53)`
- `Popular Products` — Unassigned — `urn:li:chart:(looker,b2fd91.dashboard_elements.221)`
- `Promotions` — Unassigned — `urn:li:chart:(looker,b2fd91.dashboard_elements.222)`
- `Order Mode` — Unassigned — `urn:li:chart:(looker,b2fd91.dashboard_elements.223)`
- `Orders by Day` — Unassigned — `urn:li:chart:(looker,b2fd91.dashboard_elements.224)`
- `Customer Analysis` — Unassigned — `urn:li:chart:(powerbi,b2fd91.pages.66666666-7777-8888-9999-000000000000.217abe0d5c1cd421c384)`
- `Geographics` — Unassigned — `urn:li:chart:(powerbi,b2fd91.pages.66666666-7777-8888-9999-000000000000.3f48c0bf859b2d14dcd0)`
- `Executive Summary` — Unassigned — `urn:li:chart:(powerbi,b2fd91.pages.66666666-7777-8888-9999-000000000000.83a9aaa3207edd6c721e)`
- `DAX Visual` — Unassigned — `urn:li:chart:(powerbi,b2fd91.pages.66666666-7777-8888-9999-000000000000.85e432543b30346a0507)`

## Exit criteria

All 25 recorded consumers must complete migration through `order_details__changesafe`, the operation-specific compatibility test must remain green, and the accountable owner must approve phase two.
