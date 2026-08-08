import json
from decimal import Decimal

import httpx
import pytest
import respx

from changesafe.context.replay import ReplayDataHubContext
from changesafe.domain import ChangeOperation, ChangeRequest, LlmUsage
from changesafe.generation.openai_generator import (
    GenerationPlanningError,
    OpenAIGenerationPlanner,
)
from changesafe.generation.service import ArtifactGenerationService
from changesafe.generation.templates import GenerationNarrative
from changesafe.risk import score_change

TARGET = "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.dim_customers,PROD)"


async def inputs():
    change = ChangeRequest(
        asset_urn=TARGET,
        operation=ChangeOperation.RENAME,
        field="customer_email",
        new_field="primary_email",
        old_type="STRING",
        new_type="STRING",
        source_commit="demo-unsafe-change",
        requested_by="demo-user",
    )
    context = await ReplayDataHubContext.from_default().load(change)
    return change, context, score_change(change, context)


def openai_response(narrative: GenerationNarrative) -> dict:
    return {
        "id": "resp_changesafe_test",
        "object": "response",
        "created_at": 1786219200,
        "status": "completed",
        "background": False,
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": 1800,
        "model": "gpt-5.6-luna",
        "output": [
            {
                "id": "msg_changesafe_test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": narrative.model_dump_json(),
                        "annotations": [],
                    }
                ],
            }
        ],
        "parallel_tool_calls": True,
        "previous_response_id": None,
        "reasoning": {"effort": "none", "summary": None},
        "store": False,
        "temperature": 1.0,
        "text": {"format": {"type": "text"}, "verbosity": "medium"},
        "tool_choice": "auto",
        "tools": [],
        "top_p": 1.0,
        "truncation": "disabled",
        "usage": {
            "input_tokens": 120,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 90,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 210,
        },
        "user": None,
        "metadata": {},
    }


@pytest.mark.asyncio
@respx.mock
async def test_openai_planner_uses_strict_bounded_response_schema() -> None:
    expected = GenerationNarrative(
        transformation_expression="lower(customer_email)",
        explanation="Normalize the compatibility value.",
        deprecation_language="Retain the old field for 30 days.",
        migration_summary="Expose both names during phase one.",
        rollback_summary="Revert the model, YAML, and singular test.",
        pr_prose="Adds a validated compatibility alias.",
    )
    route = respx.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(200, json=openai_response(expected))
    )
    change, context, risk = await inputs()
    planner = OpenAIGenerationPlanner(api_key="test-key", model="gpt-5.6-luna")

    result = await planner.plan(change, context, risk)

    assert result.narrative == expected
    assert result.usage.input_tokens == 120
    assert result.usage.output_tokens == 90
    assert result.usage.total_tokens == 210
    assert result.usage.estimated_cost_usd == Decimal("0.0066")
    request = json.loads(route.calls[0].request.content)
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["strict"] is True
    assert request["max_output_tokens"] == 1800


class FailingPlanner:
    async def plan(self, change, context, risk):
        raise TimeoutError("simulated external timeout")


@pytest.mark.asyncio
@respx.mock
async def test_openai_planner_blocks_oversized_input_before_network_call() -> None:
    planner = OpenAIGenerationPlanner(
        api_key="test-key",
        model="gpt-5.6-luna",
        max_input_tokens=512,
    )

    with pytest.raises(GenerationPlanningError, match="token ceiling"):
        await planner._request({"untrusted_context": "x" * 2_000})

    assert len(respx.calls) == 0


@pytest.mark.asyncio
async def test_openai_planner_wraps_malformed_usage_as_planning_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planner = OpenAIGenerationPlanner(api_key="test-key", model="gpt-5.6-luna")
    change, context, risk = await inputs()

    async def malformed_usage(*_args, **_kwargs):
        return "{}", LlmUsage(
            model="gpt-5.6-luna",
            request_count=1,
            input_tokens=-1,
            output_tokens=0,
            total_tokens=0,
            estimated_cost_usd=Decimal("0"),
        )

    monkeypatch.setattr(planner, "_request", malformed_usage)

    with pytest.raises(GenerationPlanningError, match="planning request failed"):
        await planner.plan(change, context, risk)


@pytest.mark.asyncio
async def test_unknown_repair_usage_retains_the_full_budget_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planner = OpenAIGenerationPlanner(api_key="test-key", model="gpt-5.6-luna")
    first_usage = LlmUsage(
        model="gpt-5.6-luna",
        request_count=1,
        input_tokens=120,
        output_tokens=10,
        total_tokens=130,
        estimated_cost_usd=Decimal("0.0018"),
    )
    call_count = 0

    async def request_with_unknown_repair(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "not valid json", first_usage
        raise GenerationPlanningError("repair response omitted usage telemetry")

    monkeypatch.setattr(planner, "_request", request_with_unknown_repair)
    change, context, risk = await inputs()
    service = ArtifactGenerationService(planner=planner)

    result = await service.generate_with_usage(change, context, risk)

    assert call_count == 2
    assert result.usage is None
    assert result.release_reservation is False


@pytest.mark.asyncio
async def test_generation_service_falls_back_to_conservative_templates() -> None:
    change, context, risk = await inputs()
    service = ArtifactGenerationService(planner=FailingPlanner())

    bundle = await service.generate(change, context, risk)

    assert len(bundle.files) == 7
    assert (
        "customer_email as primary_email"
        in bundle.files["models/marts/dim_customers.sql"].content.lower()
    )
