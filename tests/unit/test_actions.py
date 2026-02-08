"""Tests for step actions."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from botengine.actions import ExecutionContext, render_template
from botengine.actions.click import ClickAction
from botengine.actions.extract import ExtractAction
from botengine.actions.fill import FillAction
from botengine.actions.navigate import NavigateAction
from botengine.actions.registry import ACTION_REGISTRY, get_action
from botengine.actions.screenshot import ScreenshotAction
from botengine.actions.wait import WaitAction
from botengine.models import (
    FlowStep,
    PostConditions,
    StepAction,
    TargetSelector,
)
from botengine.resolver import ResolverCascade


class TestTemplateSubstitution:
    def test_simple_param(self) -> None:
        result = render_template(
            "Hello {{params.name}}",
            {"params": {"name": "World"}},
        )
        assert result == "Hello World"

    def test_extracted_value(self) -> None:
        result = render_template(
            "Token: {{extracted.token}}",
            {"params": {}, "extracted": {"token": "abc123"}},
        )
        assert result == "Token: abc123"

    def test_multiple_substitutions(self) -> None:
        result = render_template(
            "{{params.first}} {{params.last}}",
            {"params": {"first": "John", "last": "Doe"}},
        )
        assert result == "John Doe"

    def test_no_template(self) -> None:
        result = render_template("plain text", {"params": {}})
        assert result == "plain text"


def _mock_resolver(element: AsyncMock) -> ResolverCascade:
    """Create a mock resolver that always returns the given element."""
    cascade = MagicMock(spec=ResolverCascade)
    cascade.resolve = AsyncMock(return_value=(element, "css"))
    return cascade


def _mock_page() -> AsyncMock:
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"PNG")
    return page


def _mock_element() -> AsyncMock:
    el = AsyncMock()
    el.click = AsyncMock()
    el.fill = AsyncMock()
    el.text_content = AsyncMock(return_value="extracted text")
    return el


class TestNavigateAction:
    async def test_navigates_to_url(self) -> None:
        page = _mock_page()
        step = FlowStep(id="nav1", action=StepAction.NAVIGATE, url="https://example.com")
        ctx = ExecutionContext()
        result = await NavigateAction().execute(page, step, ctx)
        assert result.status == "success"
        page.goto.assert_called_once()

    async def test_template_in_url(self) -> None:
        page = _mock_page()
        step = FlowStep(
            id="nav1",
            action=StepAction.NAVIGATE,
            url="https://{{params.domain}}/login",
        )
        ctx = ExecutionContext(params={"domain": "example.com"})
        result = await NavigateAction().execute(page, step, ctx)
        assert result.status == "success"
        call_args = page.goto.call_args
        assert "example.com" in call_args[0][0]


class TestClickAction:
    async def test_clicks_element(self) -> None:
        page = _mock_page()
        element = _mock_element()
        step = FlowStep(
            id="c1",
            action=StepAction.CLICK,
            target=TargetSelector(css="#btn"),
        )
        ctx = ExecutionContext(resolver=_mock_resolver(element))
        result = await ClickAction().execute(page, step, ctx)
        assert result.status == "success"
        assert result.resolution_strategy == "css"
        element.click.assert_called_once()

    async def test_checks_post_conditions(self) -> None:
        page = _mock_page()
        element = _mock_element()
        step = FlowStep(
            id="c1",
            action=StepAction.CLICK,
            target=TargetSelector(css="#btn"),
            post_conditions=PostConditions(element_appears="#dashboard"),
        )
        ctx = ExecutionContext(resolver=_mock_resolver(element))
        result = await ClickAction().execute(page, step, ctx)
        assert result.status == "success"
        page.wait_for_selector.assert_called_once()

    async def test_fails_without_target(self) -> None:
        page = _mock_page()
        step = FlowStep(id="c1", action=StepAction.CLICK)
        ctx = ExecutionContext()
        result = await ClickAction().execute(page, step, ctx)
        assert result.status == "failed"


class TestFillAction:
    async def test_fills_input(self) -> None:
        page = _mock_page()
        element = _mock_element()
        step = FlowStep(
            id="f1",
            action=StepAction.FILL,
            target=TargetSelector(css="#email"),
            value="user@test.com",
        )
        ctx = ExecutionContext(resolver=_mock_resolver(element))
        result = await FillAction().execute(page, step, ctx)
        assert result.status == "success"
        element.fill.assert_called_once_with("user@test.com", timeout=10000)

    async def test_template_in_value(self) -> None:
        page = _mock_page()
        element = _mock_element()
        step = FlowStep(
            id="f1",
            action=StepAction.FILL,
            target=TargetSelector(css="#email"),
            value="{{params.email}}",
        )
        ctx = ExecutionContext(
            params={"email": "test@example.com"},
            resolver=_mock_resolver(element),
        )
        result = await FillAction().execute(page, step, ctx)
        assert result.status == "success"
        element.fill.assert_called_once_with("test@example.com", timeout=10000)


class TestExtractAction:
    async def test_extracts_text(self) -> None:
        page = _mock_page()
        element = _mock_element()
        step = FlowStep(
            id="e1",
            action=StepAction.EXTRACT,
            target=TargetSelector(css="#result"),
            save_as="result_text",
        )
        ctx = ExecutionContext(resolver=_mock_resolver(element))
        result = await ExtractAction().execute(page, step, ctx)
        assert result.status == "success"
        assert result.extracted_value == "extracted text"
        assert ctx.extracted["result_text"] == "extracted text"


class TestWaitAction:
    async def test_waits_for_selector(self) -> None:
        page = _mock_page()
        step = FlowStep(
            id="w1",
            action=StepAction.WAIT,
            target=TargetSelector(css="#loaded"),
            timeout_ms=5000,
        )
        ctx = ExecutionContext()
        result = await WaitAction().execute(page, step, ctx)
        assert result.status == "success"
        page.wait_for_selector.assert_called_once_with("#loaded", timeout=5000)


class TestScreenshotAction:
    async def test_takes_screenshot(self, tmp_path: Path) -> None:
        page = _mock_page()
        step = FlowStep(id="ss1", action=StepAction.SCREENSHOT)
        ctx = ExecutionContext(screenshots_dir=tmp_path)
        result = await ScreenshotAction().execute(page, step, ctx)
        assert result.status == "success"
        assert result.screenshot_path is not None


class TestActionRegistry:
    def test_all_actions_registered(self) -> None:
        for action in [
            StepAction.NAVIGATE,
            StepAction.CLICK,
            StepAction.FILL,
            StepAction.EXTRACT,
            StepAction.WAIT,
            StepAction.SCREENSHOT,
        ]:
            assert action in ACTION_REGISTRY

    def test_get_action(self) -> None:
        action = get_action(StepAction.NAVIGATE)
        assert isinstance(action, NavigateAction)

    def test_get_action_unknown_raises(self) -> None:
        with pytest.raises(ValueError):
            get_action(StepAction.HOVER)
