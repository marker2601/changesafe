"""Canonical organizer-provided scenario used by replay and shared-review flows."""

from changesafe.domain import ChangeOperation, ChangeRequest

DEMO_TARGET_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:dbt,"
    "b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)"
)
DEMO_FIELD = "cust_email"
DEMO_NEW_FIELD = "primary_email"
DEMO_DATA_PRODUCT = "Order Entry Analytics"


def golden_change() -> ChangeRequest:
    """Return the deterministic schema rename shown in the public demo."""

    return ChangeRequest(
        asset_urn=DEMO_TARGET_URN,
        operation=ChangeOperation.RENAME,
        field=DEMO_FIELD,
        new_field=DEMO_NEW_FIELD,
        source_commit="showcase-ecommerce-safe-rename",
        requested_by="changesafe-demo",
    )
