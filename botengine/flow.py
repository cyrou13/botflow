"""Flow loader and runner."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from botengine.actions import ExecutionContext, render_template
from botengine.actions.registry import get_action
from botengine.browser import BrowserManager
from botengine.exceptions import (
    FlowNotFoundError,
    FlowValidationError,
    SelectorResolutionError,
    StepExecutionError,
)
from botengine.logger import get_logger
from botengine.models import Flow, FlowStep, RunResult, StepResult
from botengine.resolver import ResolverCascade

log = get_logger(__name__)


class FlowLoader:
    """Loads and validates .flow.json files."""

    def __init__(self, flows_dir: Path) -> None:
        self.flows_dir = Path(flows_dir)
        self._cache: dict[str, Flow] = {}

    def load(self, flow_id: str) -> Flow:
        """Load a flow by ID, using cache if available."""
        if flow_id in self._cache:
            return self._cache[flow_id]
        return self.reload(flow_id)

    def reload(self, flow_id: str) -> Flow:
        """Load a flow from disk, bypassing cache."""
        path = self._find_flow_file(flow_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            flow = Flow.model_validate(data)
            self._cache[flow_id] = flow
            log.info("flow_loaded", flow_id=flow_id, path=str(path))
            return flow
        except json.JSONDecodeError as exc:
            raise FlowValidationError(flow_id, f"Invalid JSON: {exc}") from exc
        except Exception as exc:
            raise FlowValidationError(flow_id, str(exc)) from exc

    def load_all(self) -> dict[str, Flow]:
        """Load all flows from the flows directory."""
        flows: dict[str, Flow] = {}
        for path in self.flows_dir.rglob("*.flow.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                flow = Flow.model_validate(data)
                flows[flow.flow_id] = flow
                self._cache[flow.flow_id] = flow
            except Exception as exc:
                log.warning("flow_load_failed", path=str(path), error=str(exc))
        return flows

    def save(self, flow: Flow) -> Path:
        """Save a flow to disk (for heal modifications)."""
        path = self.flows_dir / f"{flow.flow_id}.flow.json"
        path.write_text(
            flow.model_dump_json(indent=2, exclude_none=True),
            encoding="utf-8",
        )
        self._cache[flow.flow_id] = flow
        log.info("flow_saved", flow_id=flow.flow_id, path=str(path))
        return path

    def _find_flow_file(self, flow_id: str) -> Path:
        """Find the flow file by ID."""
        # Direct match
        direct = self.flows_dir / f"{flow_id}.flow.json"
        if direct.exists():
            return direct
        # Recursive search
        for path in self.flows_dir.rglob(f"{flow_id}.flow.json"):
            return path
        raise FlowNotFoundError(flow_id)


class FlowRunner:
    """Executes a flow step by step."""

    def __init__(
        self,
        browser: BrowserManager,
        resolver: ResolverCascade,
        loader: FlowLoader,
    ) -> None:
        self.browser = browser
        self.resolver = resolver
        self.loader = loader

    async def run(
        self, flow_id: str, params: dict[str, Any] | None = None
    ) -> RunResult:
        """Execute all steps in a flow."""
        params = params or {}
        started_at = datetime.now(tz=timezone.utc)
        start_time = time.monotonic()

        flow = self.loader.load(flow_id)
        self._validate_params(flow, params)

        page = await self.browser.get_page()
        context = ExecutionContext(
            params=params,
            resolver=self.resolver,
        )

        step_results: list[StepResult] = []
        overall_status = "success"

        for step in flow.steps:
            try:
                result = await self._execute_step(page, step, context)
                step_results.append(result)

                if result.status == "failed":
                    if step.optional:
                        step_results[-1] = StepResult(
                            step_id=result.step_id,
                            status="skipped",
                            duration_ms=result.duration_ms,
                            error=result.error,
                        )
                    else:
                        overall_status = "failed"
                        break
            except SelectorResolutionError as exc:
                step_results.append(
                    StepResult(
                        step_id=step.id,
                        status="failed",
                        duration_ms=(time.monotonic() - start_time) * 1000,
                        error=str(exc),
                    )
                )
                if not step.optional:
                    overall_status = "failed"
                    break

        # Build returns
        returns = self._build_returns(flow, context)

        if overall_status == "success" and any(
            r.status in ("skipped",) for r in step_results
        ):
            overall_status = "partial"

        finished_at = datetime.now(tz=timezone.utc)
        return RunResult(
            flow_id=flow_id,
            status=overall_status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=(time.monotonic() - start_time) * 1000,
            step_results=step_results,
            returns=returns,
        )

    async def run_step(
        self,
        flow_id: str,
        step_id: str,
        params: dict[str, Any] | None = None,
    ) -> StepResult:
        """Run a single step (for debugging)."""
        params = params or {}
        flow = self.loader.load(flow_id)
        step = next((s for s in flow.steps if s.id == step_id), None)
        if not step:
            raise StepExecutionError(step_id, "unknown", "Step not found in flow")

        page = await self.browser.get_page()
        context = ExecutionContext(params=params, resolver=self.resolver)
        return await self._execute_step(page, step, context)

    async def _execute_step(
        self, page: Any, step: FlowStep, context: ExecutionContext
    ) -> StepResult:
        """Execute a single step with its action handler."""
        action = get_action(step.action)
        try:
            result = await asyncio.wait_for(
                action.execute(page, step, context),
                timeout=step.timeout_ms / 1000,
            )
            return result
        except asyncio.TimeoutError:
            return StepResult(
                step_id=step.id,
                status="failed",
                duration_ms=step.timeout_ms,
                error=f"Step timed out after {step.timeout_ms}ms",
            )

    @staticmethod
    def _validate_params(flow: Flow, params: dict[str, Any]) -> None:
        """Validate provided params against flow param definitions."""
        for name, param_def in flow.params.items():
            if param_def.required and name not in params:
                if param_def.default is None:
                    raise FlowValidationError(
                        flow.flow_id,
                        f"Missing required parameter: {name}",
                    )

    @staticmethod
    def _build_returns(flow: Flow, context: ExecutionContext) -> dict[str, Any]:
        """Build the returns dict from the flow's returns_mapping."""
        returns: dict[str, Any] = {}
        template_ctx = {
            "params": context.params,
            "extracted": context.extracted,
        }
        for key, template in flow.returns_mapping.items():
            if isinstance(template, str) and "{{" in template:
                returns[key] = render_template(template, template_ctx)
            else:
                returns[key] = template
        return returns
