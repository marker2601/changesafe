from changesafe.redaction import redact


def test_redaction_removes_nested_secrets_without_hiding_safe_metadata() -> None:
    payload = {
        "tool": "get_lineage",
        "authorization": "Bearer live-token",
        "nested": {
            "api_key": "sk-private",
            "password": "warehouse-secret",
            "urn": "urn:li:dataset:dim_customers",
        },
        "items": [{"token": "child-token", "count": 4}],
    }

    sanitized = redact(payload)

    assert sanitized == {
        "tool": "get_lineage",
        "authorization": "[REDACTED]",
        "nested": {
            "api_key": "[REDACTED]",
            "password": "[REDACTED]",
            "urn": "urn:li:dataset:dim_customers",
        },
        "items": [{"token": "[REDACTED]", "count": 4}],
    }
