"""BotEngine — main entry point for bot automation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from botengine.browser import BrowserManager
from botengine.confidence import ConfidenceTracker
from botengine.exceptions import HealingError, StepExecutionError
from botengine.flow import FlowLoader, FlowRunner
from botengine.healer import AutoHealer
from botengine.logger import get_logger
from botengine.models import (
    FlowHealth,
    HealMode,
    HealProposal,
    RunResult,
    TargetSelector,
)
from botengine.resolver import ResolverCascade
from botengine.resolvers.llm_vision import LLMVisionResolver

log = get_logger(__name__)


class BotEngine:
    """Main entry point for bot automation."""

    def __init__(
        self,
        flows_dir: str | Path,
        headless: bool = True,
        heal_mode: HealMode = HealMode.SUPERVISED,
        on_heal: Callable[[HealProposal], Awaitable[bool]] | None = None,
        anthropic_api_key: str | None = None,
        screenshots_dir: str | Path | None = None,
        log_dir: str | Path | None = None,
    ) -> None:
        self._flows_dir = Path(flows_dir)
        self._headless = headless
        self._heal_mode = heal_mode
        self._on_heal = on_heal
        self._screenshots_dir = Path(screenshots_dir) if screenshots_dir else None
        self._log_dir = Path(log_dir) if log_dir else None

        # Core components
        self._browser = BrowserManager()
        self._loader = FlowLoader(self._flows_dir)
        self._resolver = self._build_resolver(anthropic_api_key)
        self._runner = FlowRunner(self._browser, self._resolver, self._loader)

        # Healing components
        self._anthropic_client = None
        if anthropic_api_key:
            try:
                import anthropic
                self._anthropic_client = anthropic.AsyncAnthropic(
                    api_key=anthropic_api_key
                )
            except ImportError:
                log.warning("anthropic_not_installed")

        self._healer = AutoHealer(anthropic_client=self._anthropic_client)
        state_dir = self._flows_dir / ".botflow" / "confidence"
        self._confidence = ConfidenceTracker(state_dir)

        # Per-flow heal mode overrides
        self._flow_heal_modes: dict[str, HealMode] = {}

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start the engine and browser."""
        await self._browser.start(headless=self._headless)
        log.info("engine_started", flows_dir=str(self._flows_dir))

    async def stop(self) -> None:
        """Stop the engine and browser."""
        await self._browser.stop()
        log.info("engine_stopped")

    async def __aenter__(self) -> BotEngine:
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()

    # --- Execution ---

    async def execute(
        self, flow_name: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a flow and return its declared returns."""
        result = await self.execute_full(flow_name, params)
        if result.status == "failed":
            failed_steps = [
                r for r in result.step_results if r.status == "failed"
            ]
            if failed_steps:
                raise StepExecutionError(
                    failed_steps[-1].step_id,
                    "unknown",
                    failed_steps[-1].error or "Step failed",
                )
        return result.returns

    async def execute_full(
        self, flow_name: str, params: dict[str, Any] | None = None
    ) -> RunResult:
        """Execute and return full RunResult with all details."""
        result = await self._runner.run(flow_name, params)

        # Handle healing for failed steps
        if result.status == "failed":
            heal_mode = self._get_heal_mode(flow_name)
            if heal_mode != HealMode.OFF:
                result = await self._attempt_healing(flow_name, result, params)

        return result

    async def _attempt_healing(
        self,
        flow_name: str,
        result: RunResult,
        params: dict[str, Any] | None,
    ) -> RunResult:
        """Attempt to heal failed steps and retry."""
        heal_mode = self._get_heal_mode(flow_name)
        heals_triggered = 0

        for step_result in result.step_results:
            if step_result.status != "failed":
                continue

            flow = self._loader.load(flow_name)
            step = next(
                (s for s in flow.steps if s.id == step_result.step_id), None
            )
            if not step or not isinstance(step.target, TargetSelector):
                continue

            try:
                screenshot = await self._browser.screenshot()
                dom = await self._browser.get_dom_snapshot()

                proposal = await self._healer.propose_heal(
                    step, screenshot, dom, step_result.error or "Unknown error"
                )
                heals_triggered += 1

                should_apply = False
                if heal_mode == HealMode.AUTO:
                    should_apply = self._confidence.should_auto_heal(
                        flow_name, proposal.confidence_score
                    )
                elif heal_mode == HealMode.SUPERVISED and self._on_heal:
                    should_apply = await self._on_heal(proposal)

                if should_apply:
                    await self._healer.apply_heal(
                        self._loader, flow_name, proposal
                    )
                    self._confidence.record_heal_success(flow_name)
                    # Retry the flow
                    retry_result = await self._runner.run(flow_name, params)
                    retry_result.heals_triggered = heals_triggered
                    return retry_result
                else:
                    self._confidence.record_heal_failure(flow_name)

            except HealingError as exc:
                log.warning("healing_failed", flow=flow_name, error=str(exc))
                self._confidence.record_heal_failure(flow_name)

        result.heals_triggered = heals_triggered
        return result

    # --- Status ---

    def flow_health(self) -> dict[str, FlowHealth]:
        """Get health status for all flows."""
        flows = self._loader.load_all()
        health: dict[str, FlowHealth] = {}
        for flow_id in flows:
            state = self._confidence.get_state(flow_id)
            health[flow_id] = FlowHealth(
                flow_id=flow_id,
                heal_mode=self._get_heal_mode(flow_id),
                auto_heal_threshold=state.auto_threshold,
            )
        return health

    def list_flows(self) -> list[str]:
        """List all available flow IDs."""
        flows = self._loader.load_all()
        return list(flows.keys())

    # --- Configuration ---

    def set_heal_mode(
        self, flow_name: str | None, mode: HealMode
    ) -> None:
        """Set heal mode globally or for a specific flow."""
        if flow_name:
            self._flow_heal_modes[flow_name] = mode
        else:
            self._heal_mode = mode

    def set_confidence_threshold(
        self, flow_name: str, threshold: float
    ) -> None:
        """Manually set the confidence threshold for a flow."""
        state = self._confidence.get_state(flow_name)
        state.auto_threshold = threshold
        self._confidence._save_state(state)

    # --- Private helpers ---

    def _get_heal_mode(self, flow_name: str) -> HealMode:
        """Get the effective heal mode for a flow."""
        return self._flow_heal_modes.get(flow_name, self._heal_mode)

    @staticmethod
    def _build_resolver(api_key: str | None) -> ResolverCascade:
        """Build the resolver cascade, adding LLM resolver if API key available."""
        from botengine.resolvers.aria import AriaResolver
        from botengine.resolvers.css import CSSResolver
        from botengine.resolvers.fuzzy import FuzzyTextResolver
        from botengine.resolvers.text import TextResolver
        from botengine.resolvers.xpath import XPathResolver

        resolvers = [
            CSSResolver(),
            XPathResolver(),
            TextResolver(),
            AriaResolver(),
            FuzzyTextResolver(),
        ]

        if api_key:
            try:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=api_key)
                resolvers.append(LLMVisionResolver(client=client))
            except ImportError:
                pass

        return ResolverCascade(resolvers=resolvers)
