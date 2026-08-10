from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
BLUEPRINT = ROOT / "render.yaml"
README = ROOT / "README.md"
DEPLOY_URL = (
    "https://render.com/deploy?repo="
    "https://github.com/marker2601/changesafe"
)
HOSTED_URL = "https://changesafe-competition.onrender.com"

EXPECTED_ENV = {
    "CHANGESAFE_DATA_PATH": "/data/changesafe.db",
    "CHANGESAFE_LIVE_EVIDENCE_REQUIRED": "false",
    "CHANGESAFE_MODE": "replay",
    "CHANGESAFE_RUNS_PER_MINUTE": "30",
    "CHANGESAFE_WAREHOUSE_VALIDATION_ENABLED": "false",
    "CHANGESAFE_WAREHOUSE_VALIDATION_REQUIRED": "false",
    "CHANGESAFE_WEB_DIST": "/app/web",
    "PORT": "8000",
    "PUBLIC_PR_ENABLED": "false",
    "PUBLIC_WRITEBACK_ENABLED": "false",
}


def load_service() -> dict[str, Any]:
    document = yaml.safe_load(BLUEPRINT.read_text(encoding="utf-8"))
    assert list(document) == ["services"]
    assert len(document["services"]) == 1
    return document["services"][0]


def test_render_blueprint_deploys_the_existing_container_safely() -> None:
    service = load_service()
    assert service["type"] == "web"
    assert service["name"] == "changesafe-competition"
    assert service["runtime"] == "docker"
    assert service["plan"] == "free"
    assert service["region"] == "ohio"
    assert service["branch"] == "master"
    assert service["autoDeployTrigger"] == "checksPass"
    assert service["dockerfilePath"] == "./Dockerfile"
    assert service["dockerContext"] == "."
    assert service["healthCheckPath"] == "/healthz"
    assert service["renderSubdomainPolicy"] == "enabled"
    assert "maxShutdownDelaySeconds" not in service
    assert "disk" not in service


def test_render_blueprint_contains_only_public_safe_environment() -> None:
    service = load_service()
    environment = {item["key"]: item["value"] for item in service["envVars"]}
    assert environment == EXPECTED_ENV
    forbidden_fragments = ("TOKEN", "PASSWORD", "PRIVATE_KEY", "SECRET")
    assert not any(
        fragment in key
        for key in environment
        for fragment in forbidden_fragments
    )


def test_readme_exposes_truthful_render_deployment() -> None:
    readme = README.read_text(encoding="utf-8")
    assert HOSTED_URL in readme
    assert DEPLOY_URL in readme
    assert "competition-ready pilot" in readme
    assert "Recorded DataHub evidence" in readme
    assert "free service can sleep" in readme
    assert "may clear earlier run history" in readme
    assert "publicly reachable DataHub GMS URL" in readme
