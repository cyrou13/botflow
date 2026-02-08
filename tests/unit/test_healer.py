"""Tests for the auto-healer."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from botengine.exceptions import HealingError
from botengine.flow import FlowLoader
from botengine.healer import AutoHealer
from botengine.models import (
    Flow,
    FlowStep,
    HealProposal,
    StepAction,
    TargetSelector,
)


class TestBuildPrompt:
    def test_includes_step_info(self) -> None:
        step = FlowStep(
            id="s1",
            action=StepAction.CLICK,
            description="Click the login button",
            target=TargetSelector(css="#login", text_content="Login"),
        )
        prompt = AutoHealer._build_heal_prompt(step, "<html></html>", "Not found")
        assert "Click the login button" in prompt
        assert "#login" in prompt
        assert "Login" in prompt
        assert "Not found" in prompt

    def test_handles_no_target(self) -> None:
        step = FlowStep(
            id="s1",
            action=StepAction.CLICK,
            description="Click something",
        )
        prompt = AutoHealer._build_heal_prompt(step, "<html></html>", "Error")
        assert "Click something" in prompt


class TestParseResponse:
    def test_parse_valid_json(self) -> None:
        response = json.dumps({
            "css": "#new-btn",
            "xpath": "//button",
            "confidence": 85,
            "reasoning": "Found by ID",
        })
        result = AutoHealer._parse_response(response)
        assert result["css"] == "#new-btn"
        assert result["confidence"] == 85

    def test_parse_json_in_code_fence(self) -> None:
        response = '```json\n{"css": "#btn", "confidence": 90, "reasoning": "x"}\n```'
        result = AutoHealer._parse_response(response)
        assert result["css"] == "#btn"

    def test_parse_json_embedded_in_text(self) -> None:
        response = 'Here is the result: {"css": "#x", "confidence": 70, "reasoning": "y"} done.'
        result = AutoHealer._parse_response(response)
        assert result["css"] == "#x"

    def test_parse_invalid_raises(self) -> None:
        with pytest.raises(HealingError):
            AutoHealer._parse_response("not json at all")


class TestProposeHeal:
    async def test_raises_without_client(self) -> None:
        healer = AutoHealer(anthropic_client=None)
        step = FlowStep(
            id="s1",
            action=StepAction.CLICK,
            target=TargetSelector(css="#old"),
        )
        with pytest.raises(HealingError, match="No Anthropic client"):
            await healer.propose_heal(step, b"screenshot", "<html></html>", "error")

    async def test_proposes_heal_with_mock_client(self) -> None:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps({
                    "css": "#new-selector",
                    "xpath": "//div[@id='new']",
                    "text_content": "New Text",
                    "aria_label": "New Label",
                    "confidence": 92,
                    "reasoning": "Element was renamed",
                })
            )
        ]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        healer = AutoHealer(anthropic_client=mock_client)
        step = FlowStep(
            id="s1",
            action=StepAction.CLICK,
            description="Click button",
            target=TargetSelector(css="#old-btn"),
        )

        proposal = await healer.propose_heal(
            step, b"fake-screenshot", "<html></html>", "Element not found"
        )
        assert isinstance(proposal, HealProposal)
        assert proposal.new_target.css == "#new-selector"
        assert proposal.confidence_score == 92
        assert proposal.old_target.css == "#old-btn"


class TestApplyHeal:
    async def test_applies_heal_to_flow(self, tmp_path: Path) -> None:
        flow = Flow(
            flow_id="test_flow",
            site="test.com",
            steps=[
                FlowStep(
                    id="s1",
                    action=StepAction.CLICK,
                    target=TargetSelector(css="#old"),
                ),
            ],
        )
        loader = FlowLoader(tmp_path)
        loader.save(flow)

        proposal = HealProposal(
            step_id="s1",
            old_target=TargetSelector(css="#old"),
            new_target=TargetSelector(css="#new", xpath="//div[@id='new']"),
            confidence_score=90,
            reasoning="ID changed",
        )

        healer = AutoHealer()
        await healer.apply_heal(loader, "test_flow", proposal)

        reloaded = loader.reload("test_flow")
        assert reloaded.steps[0].target.css == "#new"

    async def test_apply_heal_missing_step_raises(self, tmp_path: Path) -> None:
        flow = Flow(
            flow_id="test_flow",
            site="test.com",
            steps=[
                FlowStep(id="s1", action=StepAction.NAVIGATE, url="/"),
            ],
        )
        loader = FlowLoader(tmp_path)
        loader.save(flow)

        proposal = HealProposal(
            step_id="nonexistent",
            old_target=TargetSelector(),
            new_target=TargetSelector(css="#x"),
            confidence_score=80,
            reasoning="test",
        )

        healer = AutoHealer()
        with pytest.raises(HealingError, match="not found"):
            await healer.apply_heal(loader, "test_flow", proposal)
