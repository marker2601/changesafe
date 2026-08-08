"""Optional bounded OpenAI planner; deterministic templates remain authoritative."""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from changesafe.domain import ChangeRequest, ContextBundle, RiskResult
from changesafe.generation.templates import GenerationNarrative


class GenerationPlanningError(RuntimeError):
    """The optional planning call failed without affecting template availability."""


SYSTEM_INSTRUCTIONS = """You provide bounded migration planning fields for ChangeSafe.
The deterministic risk score and required files are authoritative and immutable.
Do not propose removing the old field during phase one. Do not emit Markdown fences.
Return only the strict requested schema. Keep every statement grounded in the
supplied JSON.
"""


class OpenAIGenerationPlanner:
    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, timeout=10.0, max_retries=0)

    def _payload(
        self, change: ChangeRequest, context: ContextBundle, risk: RiskResult
    ) -> dict[str, Any]:
        return {
            "change": change.model_dump(mode="json"),
            "target": {
                "urn": context.target_urn,
                "name": context.target_name,
                "field_type": context.field_type,
                "owner_names": [owner.name for owner in context.owners],
                "field_tags": context.field_tags,
                "glossary_terms": context.glossary_terms,
                "usage_tier": context.usage_tier,
            },
            "downstream": [
                {
                    "urn": asset.urn,
                    "name": asset.name,
                    "entity_type": asset.entity_type,
                    "domain": asset.domain,
                }
                for asset in context.downstream_assets
            ],
            "risk": risk.model_dump(mode="json"),
            "constraints": {
                "phase_one_keeps_old_field": True,
                "required_deprecation_days": 30,
                "risk_is_immutable": True,
            },
        }

    async def _request(
        self, payload: dict[str, Any], validation_error: str | None = None
    ) -> str:
        user_payload: dict[str, Any] = {"context": payload}
        if validation_error:
            user_payload["previous_validation_error"] = validation_error
        response = await self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, sort_keys=True),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "changesafe_generation",
                    "strict": True,
                    "schema": GenerationNarrative.model_json_schema(),
                }
            },
            max_output_tokens=1800,
            store=False,
        )
        if not response.output_text:
            raise GenerationPlanningError("OpenAI returned no structured planning text")
        return response.output_text

    async def plan(
        self, change: ChangeRequest, context: ContextBundle, risk: RiskResult
    ) -> GenerationNarrative:
        payload = self._payload(change, context, risk)
        try:
            first = await self._request(payload)
            return GenerationNarrative.model_validate_json(first)
        except ValidationError as first_error:
            try:
                repaired = await self._request(payload, str(first_error))
                return GenerationNarrative.model_validate_json(repaired)
            except Exception as exc:
                raise GenerationPlanningError(
                    "OpenAI planning failed structured validation twice"
                ) from exc
        except GenerationPlanningError:
            raise
        except Exception as exc:
            raise GenerationPlanningError("OpenAI planning request failed") from exc
