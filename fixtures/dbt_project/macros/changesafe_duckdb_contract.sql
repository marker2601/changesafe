{#
  ChangeSafe publishes warehouse-native contract types exactly as DataHub reports
  them. This fixture runs those same bytes against DuckDB, so translate only the
  contract DDL used by the local proof adapter. The generated SQL and YAML remain
  untouched and are still byte-checked by scripts/regenerate_examples.py.
#}

{% macro changesafe_duckdb_contract_type(data_type) -%}
  {%- set normalized = data_type | trim | upper -%}
  {%- if normalized == 'NUMBER' -%}
    {{ return('DECIMAL(38, 0)') }}
  {%- elif normalized.startswith('NUMBER(') -%}
    {{ return('DECIMAL' ~ normalized[6:]) }}
  {%- elif normalized in ('TEXT', 'STRING') -%}
    {{ return('VARCHAR') }}
  {%- elif normalized == 'FLOAT' -%}
    {{ return('DOUBLE') }}
  {%- elif normalized in ('TIMESTAMP_LTZ', 'TIMESTAMP_NTZ') -%}
    {{ return('TIMESTAMP') }}
  {%- elif normalized == 'TIMESTAMP_TZ' -%}
    {{ return('TIMESTAMPTZ') }}
  {%- elif normalized in (
      'BOOLEAN', 'DATE', 'DOUBLE', 'INTEGER', 'TIMESTAMP', 'TIMESTAMPTZ',
      'VARCHAR'
    ) or normalized.startswith('VARCHAR(') or normalized.startswith('DECIMAL(') -%}
    {{ return(normalized) }}
  {%- else -%}
    {{ exceptions.raise_compiler_error(
      'The local DuckDB proof does not define a safe mapping for contract type '
      ~ data_type
    ) }}
  {%- endif -%}
{%- endmacro %}

{% macro changesafe_duckdb_contract_columns(columns) -%}
  {%- set mapped = {} -%}
  {%- for key, column in columns.items() -%}
    {%- set mapped_column = fromjson(tojson(column)) -%}
    {%- do mapped_column.update({
      'data_type': changesafe_duckdb_contract_type(column['data_type'])
    }) -%}
    {%- do mapped.update({key: mapped_column}) -%}
  {%- endfor -%}
  {{ return(mapped) }}
{%- endmacro %}

{% macro duckdb__get_empty_schema_sql(columns) -%}
  {{ return(default__get_empty_schema_sql(
    changesafe_duckdb_contract_columns(columns)
  )) }}
{%- endmacro %}

{% macro duckdb__get_table_columns_and_constraints() -%}
  {%- set mapped_columns = changesafe_duckdb_contract_columns(model['columns']) -%}
  {%- set raw_column_constraints = adapter.render_raw_columns_constraints(
    raw_columns=mapped_columns
  ) -%}
  {%- set raw_model_constraints = adapter.render_raw_model_constraints(
    raw_constraints=model['constraints']
  ) -%}
  (
  {% for constraint in raw_column_constraints -%}
    {{ constraint }}{{ ',' if not loop.last or raw_model_constraints }}
  {% endfor %}
  {% for constraint in raw_model_constraints -%}
    {{ constraint }}{{ ',' if not loop.last }}
  {% endfor -%}
  )
{%- endmacro %}
