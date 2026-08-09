{{ config(materialized='table') }}

select * from {{ ref('stg_order_details') }}
