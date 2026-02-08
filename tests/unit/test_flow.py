"""Tests for flow loader and runner."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from botengine.exceptions import FlowNotFoundError, FlowValidationError
from botengine.flow import FlowLoader, FlowRunner
from botengine.models import Flow, FlowStep, StepAction, TargetSelector
from botengine.resolver import ResolverCascade


class TestFlowLoader:
    def test_load_from_fixture(self, sample_flow_path: Path) -> None:
        loader = FlowLoader(sample_flow_path)
        flow = loader.load("test_login_and_extract")
        assert flow.flow_id == "test_login_and_extract"
        assert len(flow.steps) == 4

    def test_load_caches(self, sample_flow_path: Path) -> None:
        loader = FlowLoader(sample_flow_path)
        flow1 = loader.load("test_login_and_extract")
        flow2 = loader.load("test_login_and_extract")
        assert flow1 is flow2

    def test_reload_bypasses_cache(self, sample_flow_path: Path) -> None:
        loader = FlowLoader(sample_flow_path)
        flow1 = loader.load("test_login_and_extract")
        flow2 = loader.reload("test_login_and_extract")
        assert flow1 is not flow2

    def test_load_not_found_raises(self, tmp_path: Path) -> None:
        loader = FlowLoader(tmp_path)
        with pytest.raises(FlowNotFoundError):
            loader.load("nonexistent")

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.flow.json"
        bad_file.write_text("not json{")
        loader = FlowLoader(tmp_path)
        with pytest.raises(FlowValidationError):
            loader.load("bad")

    def test_load_all(self, sample_flow_path: Path) -> None:
        loader = FlowLoader(sample_flow_path)
        flows = loader.load_all()
        assert "test_login_and_extract" in flows

    def test_save(self, tmp_path: Path) -> None:
        flow = Flow(
            flow_id="saved_flow",
            site="test.com",
            steps=[FlowStep(id="s1", action=StepAction.NAVIGATE, url="/")],
        )
        loader = FlowLoader(tmp_path)
        path = loader.save(flow)
        assert path.exists()
        reloaded = loader.reload("saved_flow")
        assert reloaded.flow_id == "saved_flow"


class TestFlowRunner:
    def _mock_browser(self) -> MagicMock:
        browser = MagicMock()
        page = AsyncMock()
        page.goto = AsyncMock()
        page.query_selector = AsyncMock(return_value=AsyncMock())
        page.wait_for_selector = AsyncMock()
        browser.get_page = AsyncMock(return_value=page)
        return browser

    def _mock_resolver(self) -> MagicMock:
        element = AsyncMock()
        element.click = AsyncMock()
        element.fill = AsyncMock()
        element.text_content = AsyncMock(return_value="Welcome testuser")
        resolver = MagicMock(spec=ResolverCascade)
        resolver.resolve = AsyncMock(return_value=(element, "css"))
        return resolver

    async def test_run_simple_flow(self, sample_flow_path: Path) -> None:
        browser = self._mock_browser()
        resolver = self._mock_resolver()
        loader = FlowLoader(sample_flow_path)
        runner = FlowRunner(browser, resolver, loader)

        result = await runner.run(
            "test_login_and_extract",
            params={"username": "testuser", "password": "pass123"},
        )
        assert result.status == "success"
        assert len(result.step_results) == 4
        assert all(r.status == "success" for r in result.step_results)

    async def test_run_extracts_returns(self, sample_flow_path: Path) -> None:
        browser = self._mock_browser()
        resolver = self._mock_resolver()
        loader = FlowLoader(sample_flow_path)
        runner = FlowRunner(browser, resolver, loader)

        result = await runner.run(
            "test_login_and_extract",
            params={"username": "testuser", "password": "pass123"},
        )
        assert "welcome_text" in result.returns

    async def test_missing_required_param_raises(
        self, sample_flow_path: Path
    ) -> None:
        browser = self._mock_browser()
        resolver = self._mock_resolver()
        loader = FlowLoader(sample_flow_path)
        runner = FlowRunner(browser, resolver, loader)

        with pytest.raises(FlowValidationError, match="Missing required"):
            await runner.run("test_login_and_extract", params={})

    async def test_run_step_single(self, sample_flow_path: Path) -> None:
        browser = self._mock_browser()
        resolver = self._mock_resolver()
        loader = FlowLoader(sample_flow_path)
        runner = FlowRunner(browser, resolver, loader)

        result = await runner.run_step(
            "test_login_and_extract",
            "s_001",
            params={"username": "testuser", "password": "pass123"},
        )
        assert result.step_id == "s_001"
        assert result.status == "success"

    async def test_optional_step_skipped_on_failure(
        self, tmp_path: Path
    ) -> None:
        flow = Flow(
            flow_id="optional_test",
            site="test",
            steps=[
                FlowStep(id="s1", action=StepAction.NAVIGATE, url="/"),
                FlowStep(
                    id="s2",
                    action=StepAction.CLICK,
                    target=TargetSelector(css="#missing"),
                    optional=True,
                ),
                FlowStep(id="s3", action=StepAction.NAVIGATE, url="/done"),
            ],
        )
        loader = FlowLoader(tmp_path)
        loader.save(flow)

        browser = self._mock_browser()

        # Make resolver fail for the click step
        resolver = MagicMock(spec=ResolverCascade)
        element = AsyncMock()
        element.click = AsyncMock(side_effect=Exception("click failed"))
        resolver.resolve = AsyncMock(return_value=(element, "css"))

        runner = FlowRunner(browser, resolver, loader)
        result = await runner.run("optional_test")
        # Should not be "failed" because the failing step is optional
        assert result.status in ("success", "partial")
        assert any(r.status == "skipped" for r in result.step_results)
