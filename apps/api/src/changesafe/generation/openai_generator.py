"""Optional bounded OpenAI planner; deterministic templates remain authoritative."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Literal

from openai import APIStatusError, AsyncOpenAI
from pydantic import ValidationError

from changesafe.domain import ChangeRequest, ContextBundle, LlmUsage, RiskResult
from changesafe.generation.templates import GenerationNarrative


class GenerationPlanningError(RuntimeError):
    """The optional planning call failed without affecting template availability."""

    def __init__(
        self,
        message: str,
        *,
        usage: LlmUsage | None = None,
        charge_status: Literal["none", "unknown"] = "unknown",
        usage_complete: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.usage = usage
        self.charge_status = charge_status
        self.usage_complete = (
            charge_status == "none" if usage_complete is None else usage_complete
        )


class PlanningResult:
    def __init__(self, narrative: GenerationNarrative, usage: LlmUsage) -> None:
        self.narrative = narrative
        self.usage = usage


SYSTEM_INSTRUCTIONS = """You provide bounded migration planning fields for ChangeSafe.
The deterministic risk score and required files are authoritative and immutable.
Do not propose removing the old field during phase one. Do not emit Markdown fences.
Return only the strict requested schema. Keep every statement grounded in the
supplied JSON.
"""


class OpenAIGenerationPlanner:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        input_cost_per_million_usd: Decimal = Decimal("10"),
        output_cost_per_million_usd: Decimal = Decimal("60"),
        max_input_tokens: int = 16_000,
        max_output_tokens: int = 1_800,
    ) -> None:
        self.model = model
        self.input_cost_per_million_usd = input_cost_per_million_usd
        self.output_cost_per_million_usd = output_cost_per_million_usd
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.client = AsyncOpenAI(api_key=api_key, timeout=10.0, max_retries=0)

    def _usage(self, response: Any) -> LlmUsage:
        raw = getattr(response, "usage", None)
        if raw is None:
            raise GenerationPlanningError("OpenAI returned no usage telemetry")
        input_tokens = int(getattr(raw, "input_tokens", 0))
        output_tokens = int(getattr(raw, "output_tokens", 0))
        total_tokens = int(
            getattr(raw, "total_tokens", input_tokens + output_tokens)
        )
        cost = (
            Decimal(input_tokens) * self.input_cost_per_million_usd
            + Decimal(output_tokens) * self.output_cost_per_million_usd
        ) / Decimal(1_000_000)
        return LlmUsage(
            model=self.model,
            request_count=1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
        )

    @staticmethod
    def _combine_usage(first: LlmUsage, second: LlmUsage | None) -> LlmUsage:
        if second is None:
            return first
        return LlmUsage(
            model=first.model,
            request_count=first.request_count + second.request_count,
            input_tokens=first.input_tokens + second.input_tokens,
            output_tokens=first.output_tokens + second.output_tokens,
            total_tokens=first.total_tokens + second.total_tokens,
            estimated_cost_usd=(
                first.estimated_cost_usd + second.estimated_cost_usd
            ),
        )

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
    ) -> tuple[str, LlmUsage]:
        user_payload: dict[str, Any] = {"context": payload}
        if validation_error:
            user_payload["previous_validation_error"] = validation_error
        serialized_payload = json.dumps(user_payload, sort_keys=True)
        input_messages: Any = [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": serialized_payload},
        ]
        text_format: Any = {
            "format": {
                "type": "json_schema",
                "name": "changesafe_generation",
                "strict": True,
                "schema": GenerationNarrative.model_json_schema(),
            }
        }
        accounted_request = {
            "model": self.model,
            "input": input_messages,
            "text": text_format,
            "max_output_tokens": self.max_output_tokens,
        }
        input_byte_upper_bound = len(
            json.dumps(accounted_request, sort_keys=True).encode("utf-8")
        ) + 256
        if input_byte_upper_bound > self.max_input_tokens:
            raise GenerationPlanningError(
                "OpenAI planning input exceeds the configured token ceiling",
                charge_status="none",
            )
        response = await self.client.responses.create(
            model=self.model,
            input=input_messages,
            text=text_format,
            max_output_tokens=self.max_output_tokens,
            store=False,
        )
        usage = self._usage(response)
        if not response.output_text:
            raise GenerationPlanningError(
                "OpenAI returned no structured planning text",
                usage=usage,
                usage_complete=True,
            )
        return response.output_text, usage

    async def plan(
        self, change: ChangeRequest, context: ContextBundle, risk: RiskResult
    ) -> PlanningResult:
        payload = self._payload(change, context, risk)
        try:
            first_text, first_usage = await self._request(payload)
        except GenerationPlanningError:
            raise
        except Exception as exc:
            no_charge = isinstance(exc, APIStatusError) and 400 <= exc.status_code < 500
            raise GenerationPlanningError(
                "OpenAI planning request failed",
                charge_status="none" if no_charge else "unknown",
            ) from exc

        try:
            narrative = GenerationNarrative.model_validate_json(first_text)
            return PlanningResult(narrative, first_usage)
        except ValidationError as first_error:
            repaired_usage: LlmUsage | None = None
            try:
                repaired_text, repaired_usage = await self._request(
                    payload, str(first_error)
                )
                narrative = GenerationNarrative.model_validate_json(repaired_text)
                return PlanningResult(
                    narrative,
                    self._combine_usage(first_usage, repaired_usage),
                )
            except GenerationPlanningError as exc:
                raise GenerationPlanningError(
                    "OpenAI planning failed structured validation twice",
                    usage=self._combine_usage(first_usage, exc.usage),
                    charge_status=exc.charge_status,
                    usage_complete=exc.usage_complete,
                ) from exc
            except Exception as exc:
                no_charge = (
                    isinstance(exc, APIStatusError)
                    and 400 <= exc.status_code < 500
                )
                raise GenerationPlanningError(
                    "OpenAI planning failed structured validation twice",
                    usage=self._combine_usage(first_usage, repaired_usage),
                    charge_status="none" if no_charge else "unknown",
                    usage_complete=repaired_usage is not None or no_charge,
                ) from exc
