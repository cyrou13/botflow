"""Tests for BotFlow Pydantic models."""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from botengine.models import (
    ConfidenceState,
    DynamicTarget,
    Flow,
    FlowHealth,
    FlowParam,
    FlowReturn,
    FlowStep,
    HealMode,
    HealProposal,
    PostConditions,
    PreConditions,
    RunResult,
    StepAction,
    StepResult,
    TargetSelector,
)


class TestTargetSelector:
    def test_all_none(self) -> None:
        t = TargetSelector()
        assert t.css is None
        assert t.xpath is None

    def test_with_values(self) -> None:
        t = TargetSelector(css="#btn", xpath="//button", text_content="Click me")
        assert t.css == "#btn"
        assert t.text_content == "Click me"


class TestFlowStep:
    def test_minimal_step(self) -> None:
        step = FlowStep(id="s1", action=StepAction.CLICK)
        assert step.id == "s1"
        assert step.action == StepAction.CLICK
        assert step.optional is False
        assert step.timeout_ms == 10000

    def test_navigate_step(self) -> None:
        step = FlowStep(
            id="nav1",
            action=StepAction.NAVIGATE,
            url="https://example.com",
        )
        assert step.url == "https://example.com"

    def test_fill_step_with_target(self) -> None:
        step = FlowStep(
            id="f1",
            action=StepAction.FILL,
            target=TargetSelector(css="#email"),
            value="{{params.email}}",
        )
        assert step.value == "{{params.email}}"
        assert isinstance(step.target, TargetSelector)

    def test_step_with_conditions(self) -> None:
        step = FlowStep(
            id="s1",
            action=StepAction.CLICK,
            pre_conditions=PreConditions(url_pattern="*login*"),
            post_conditions=PostConditions(element_appears="#dashboard"),
        )
        assert step.pre_conditions.url_pattern == "*login*"
        assert step.post_conditions.element_appears == "#dashboard"

    def test_step_with_dynamic_target(self) -> None:
        step = FlowStep(
            id="d1",
            action=StepAction.CLICK,
            target=DynamicTarget(strategy="find_by_text", text="Submit"),
        )
        assert isinstance(step.target, DynamicTarget)


class TestFlow:
    def test_minimal_flow(self) -> None:
        flow = Flow(
            flow_id="test",
            site="example.com",
            steps=[FlowStep(id="s1", action=StepAction.NAVIGATE, url="https://example.com")],
        )
        assert flow.flow_id == "test"
        assert flow.version == 1
        assert len(flow.steps) == 1

    def test_flow_with_params_and_returns(self) -> None:
        flow = Flow(
            flow_id="login",
            site="example.com",
            params={
                "username": FlowParam(type="string"),
                "password": FlowParam(type="string"),
            },
            returns={"token": FlowReturn(type="string")},
            steps=[FlowStep(id="s1", action=StepAction.NAVIGATE, url="/")],
        )
        assert "username" in flow.params
        assert flow.params["username"].required is True

    def test_flow_no_steps_fails(self) -> None:
        with pytest.raises(ValidationError):
            Flow(flow_id="empty", site="test", steps=[])  # type: ignore

    def test_serialization_roundtrip(self) -> None:
        flow = Flow(
            flow_id="roundtrip",
            site="test.com",
            steps=[
                FlowStep(
                    id="s1",
                    action=StepAction.FILL,
                    target=TargetSelector(css="#input"),
                    value="hello",
                ),
            ],
        )
        data = json.loads(flow.model_dump_json())
        restored = Flow.model_validate(data)
        assert restored.flow_id == flow.flow_id
        assert restored.steps[0].target.css == "#input"

    def test_from_sample_fixture(self, sample_flow_data: dict) -> None:
        flow = Flow.model_validate(sample_flow_data)
        assert flow.flow_id == "test_login_and_extract"
        assert len(flow.steps) == 4


class TestStepResult:
    def test_success_result(self) -> None:
        r = StepResult(
            step_id="s1",
            status="success",
            resolution_strategy="css",
            duration_ms=120.5,
        )
        assert r.status == "success"

    def test_failed_result_with_error(self) -> None:
        r = StepResult(
            step_id="s1",
            status="failed",
            duration_ms=5000,
            error="Element not found",
        )
        assert r.error == "Element not found"


class TestRunResult:
    def test_successful_run(self) -> None:
        now = datetime.now(tz=timezone.utc)
        r = RunResult(
            flow_id="test",
            status="success",
            started_at=now,
            finished_at=now,
            duration_ms=1500,
            step_results=[
                StepResult(step_id="s1", status="success", duration_ms=500),
                StepResult(step_id="s2", status="success", duration_ms=1000),
            ],
            returns={"token": "abc123"},
        )
        assert r.status == "success"
        assert len(r.step_results) == 2


class TestHealProposal:
    def test_valid_proposal(self) -> None:
        p = HealProposal(
            step_id="s1",
            old_target=TargetSelector(css="#old"),
            new_target=TargetSelector(css="#new"),
            confidence_score=85.0,
            reasoning="Element ID changed",
        )
        assert p.confidence_score == 85.0

    def test_confidence_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            HealProposal(
                step_id="s1",
                old_target=TargetSelector(),
                new_target=TargetSelector(),
                confidence_score=150.0,
                reasoning="bad",
            )


class TestConfidenceState:
    def test_defaults(self) -> None:
        s = ConfidenceState(flow_id="test")
        assert s.auto_threshold == 100.0
        assert s.consecutive_successful_heals == 0


class TestHealMode:
    def test_enum_values(self) -> None:
        assert HealMode.OFF == "off"
        assert HealMode.SUPERVISED == "supervised"
        assert HealMode.AUTO == "auto"


class TestFlowHealth:
    def test_defaults(self) -> None:
        h = FlowHealth(flow_id="test")
        assert h.success_rate_7d == 0.0
        assert h.heal_mode == HealMode.SUPERVISED
