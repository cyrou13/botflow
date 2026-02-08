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
from botengine.actions.type import TypeAction
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


def _mock_locator() -> MagicMock:
    """Create a mock Playwright locator with or_(), first, and wait_for() support."""
    loc = MagicMock()
    loc.or_ = MagicMock(return_value=loc)
    loc.wait_for = AsyncMock()
    loc.first = loc  # .first returns the same locator (it's a property)
    return loc


def _mock_page() -> AsyncMock:
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"PNG")
    page.locator = MagicMock(return_value=_mock_locator())
    page.get_by_text = MagicMock(return_value=_mock_locator())
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

    async def test_locator_fallback_on_element_click_fail(self) -> None:
        """When ElementHandle.click fails, locator-based click is tried first."""
        page = _mock_page()
        element = _mock_element()
        element.click = AsyncMock(side_effect=Exception("not visible"))
        css_loc = MagicMock()
        css_loc.click = AsyncMock()
        page.locator = MagicMock(return_value=css_loc)
        step = FlowStep(
            id="c1",
            action=StepAction.CLICK,
            target=TargetSelector(css="#btn", text_content="Submit"),
            timeout_ms=15000,
        )
        ctx = ExecutionContext(resolver=_mock_resolver(element))
        result = await ClickAction().execute(page, step, ctx)
        assert result.status == "success"
        # Locator fallback uses remaining budget: max(3000, 15000 - 5000 - 1000) = 9000
        page.locator.assert_called_with("#btn")
        css_loc.click.assert_called_once_with(timeout=9000)

    async def test_role_fallback_when_locator_also_fails(self) -> None:
        """When both ElementHandle and locator click fail, role fallback fires."""
        page = _mock_page()
        element = _mock_element()
        element.click = AsyncMock(side_effect=Exception("not visible"))
        css_loc = MagicMock()
        css_loc.click = AsyncMock(side_effect=Exception("locator failed"))
        page.locator = MagicMock(return_value=css_loc)
        button_loc = MagicMock()
        button_loc.click = AsyncMock()
        page.get_by_role = MagicMock(return_value=button_loc)
        step = FlowStep(
            id="c1",
            action=StepAction.CLICK,
            target=TargetSelector(css="#btn", text_content="Submit"),
            timeout_ms=15000,
        )
        ctx = ExecutionContext(resolver=_mock_resolver(element))
        result = await ClickAction().execute(page, step, ctx)
        assert result.status == "success"
        page.get_by_role.assert_called_with("button", name="Submit")
        button_loc.click.assert_called_once_with(timeout=9000)

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
        page.locator.assert_called_once_with("#loaded")

    async def test_waits_with_multiple_selectors(self) -> None:
        page = _mock_page()
        step = FlowStep(
            id="w2",
            action=StepAction.WAIT,
            target=TargetSelector(css="#loaded", xpath="//div[@id='loaded']", text_content="Hello"),
            timeout_ms=5000,
        )
        ctx = ExecutionContext()
        result = await WaitAction().execute(page, step, ctx)
        assert result.status == "success"
        # Should build a combined locator via or_()
        page.locator.assert_any_call("#loaded")
        page.locator.assert_any_call("xpath=//div[@id='loaded']")
        page.get_by_text.assert_called_once_with("Hello", exact=True)

    async def test_waits_for_url(self) -> None:
        page = _mock_page()
        step = FlowStep(
            id="w3",
            action=StepAction.WAIT,
            url="https://example.com/done",
            timeout_ms=5000,
        )
        ctx = ExecutionContext()
        result = await WaitAction().execute(page, step, ctx)
        assert result.status == "success"
        page.wait_for_url.assert_called_once_with("https://example.com/done", timeout=5000)


class TestScreenshotAction:
    async def test_takes_screenshot(self, tmp_path: Path) -> None:
        page = _mock_page()
        step = FlowStep(id="ss1", action=StepAction.SCREENSHOT)
        ctx = ExecutionContext(screenshots_dir=tmp_path)
        result = await ScreenshotAction().execute(page, step, ctx)
        assert result.status == "success"
        assert result.screenshot_path is not None


class TestTypeAction:
    async def test_types_text_char_by_char(self) -> None:
        page = _mock_page()
        page.keyboard = AsyncMock()
        page.keyboard.type = AsyncMock()
        element = _mock_element()
        step = FlowStep(
            id="t1",
            action=StepAction.TYPE,
            target=TargetSelector(css="#dob"),
            value="01/01/1990",
        )
        ctx = ExecutionContext(resolver=_mock_resolver(element))
        result = await TypeAction().execute(page, step, ctx)
        assert result.status == "success"
        assert result.resolution_strategy == "css"
        element.click.assert_called_once()
        page.keyboard.type.assert_called_once_with("01/01/1990", delay=50)

    async def test_template_in_value(self) -> None:
        page = _mock_page()
        page.keyboard = AsyncMock()
        page.keyboard.type = AsyncMock()
        element = _mock_element()
        step = FlowStep(
            id="t1",
            action=StepAction.TYPE,
            target=TargetSelector(css="#dob"),
            value="{{params.birthdate}}",
        )
        ctx = ExecutionContext(
            params={"birthdate": "25/12/1995"},
            resolver=_mock_resolver(element),
        )
        result = await TypeAction().execute(page, step, ctx)
        assert result.status == "success"
        page.keyboard.type.assert_called_once_with("25/12/1995", delay=50)

    async def test_fails_without_target(self) -> None:
        page = _mock_page()
        step = FlowStep(id="t1", action=StepAction.TYPE, value="test")
        ctx = ExecutionContext()
        result = await TypeAction().execute(page, step, ctx)
        assert result.status == "failed"


class TestActionRegistry:
    def test_all_actions_registered(self) -> None:
        for action in [
            StepAction.NAVIGATE,
            StepAction.CLICK,
            StepAction.FILL,
            StepAction.EXTRACT,
            StepAction.WAIT,
            StepAction.SCREENSHOT,
            StepAction.TYPE,
        ]:
            assert action in ACTION_REGISTRY

    def test_get_action(self) -> None:
        action = get_action(StepAction.NAVIGATE)
        assert isinstance(action, NavigateAction)

    def test_get_action_unknown_raises(self) -> None:
        with pytest.raises(ValueError):
            get_action(StepAction.HOVER)
