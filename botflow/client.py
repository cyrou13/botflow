"""BotFlow client — run automation flows locally or via remote server."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from botflow.exceptions import (
    BotFlowClientError,
    ConnectionError,
    FlowExecutionError,
    FlowNotFoundError,
    TimeoutError,
)
from botflow.models import FlowInfo, FlowResult, ParamSpec, ReturnSpec, StepOutcome


class BotFlow:
    """BotFlow client — run automation flows locally or via remote server.

    Use ``flows_dir`` for local mode (embeds BotEngine, runs Playwright locally)
    or ``server`` for remote mode (talks to the recorder server's HTTP API).
    """

    def __init__(
        self,
        *,
        flows_dir: str | Path | None = None,
        server: str | None = None,
        headless: bool = True,
        heal_mode: str = "off",
        anthropic_api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        if not flows_dir and not server:
            raise BotFlowClientError("Provide either flows_dir (local) or server (remote)")
        if flows_dir and server:
            raise BotFlowClientError("Provide flows_dir or server, not both")

        self._flows_dir = Path(flows_dir) if flows_dir else None
        self._server = server.rstrip("/") if server else None
        self._headless = headless
        self._heal_mode = heal_mode
        self._anthropic_api_key = anthropic_api_key
        self._timeout = timeout

        # Local mode state
        self._engine: Any = None

        # Remote mode state
        self._http: httpx.AsyncClient | None = None

    # --- Lifecycle ---

    async def start(self) -> None:
        """Initialize the client (start engine or HTTP session)."""
        if self._flows_dir:
            await self._start_local()
        else:
            self._http = httpx.AsyncClient(
                base_url=self._server,
                timeout=self._timeout,
            )

    async def stop(self) -> None:
        """Shut down the client."""
        if self._engine:
            await self._engine.stop()
            self._engine = None
        if self._http:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> BotFlow:
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()

    # --- Public API ---

    async def list_flows(self) -> list[str]:
        """List all available flow IDs."""
        if self._engine:
            return self._engine.list_flows()
        return await self._remote_list_flows()

    async def get_flow(self, flow_id: str) -> FlowInfo:
        """Get metadata for a specific flow."""
        if self._engine:
            return self._local_get_flow(flow_id)
        return await self._remote_get_flow(flow_id)

    async def run(self, flow_id: str, **params: Any) -> dict[str, Any]:
        """Execute a flow and return its declared returns dict."""
        if self._engine:
            return await self._local_run(flow_id, params)
        return await self._remote_run(flow_id, params)

    async def run_full(self, flow_id: str, **params: Any) -> FlowResult:
        """Execute a flow and return the full FlowResult with step details."""
        if self._engine:
            return await self._local_run_full(flow_id, params)
        return await self._remote_run_full(flow_id, params)

    # --- Local mode ---

    async def _start_local(self) -> None:
        """Start the embedded BotEngine."""
        from botengine.engine import BotEngine
        from botengine.models import HealMode

        heal = HealMode(self._heal_mode)
        self._engine = BotEngine(
            flows_dir=self._flows_dir,
            headless=self._headless,
            heal_mode=heal,
            anthropic_api_key=self._anthropic_api_key,
        )
        await self._engine.start()

    def _local_get_flow(self, flow_id: str) -> FlowInfo:
        """Get flow info from the local engine."""
        from botengine.exceptions import FlowNotFoundError as EngineFlowNotFound

        try:
            flow = self._engine._loader.load(flow_id)
        except EngineFlowNotFound:
            raise FlowNotFoundError(flow_id)

        return FlowInfo(
            flow_id=flow.flow_id,
            site=flow.site,
            params={
                name: ParamSpec(type=p.type, required=p.required, default=p.default, values=p.values)
                for name, p in flow.params.items()
            },
            returns={name: ReturnSpec(type=r.type) for name, r in flow.returns.items()},
            step_count=len(flow.steps),
        )

    async def _local_run(self, flow_id: str, params: dict[str, Any]) -> dict[str, Any]:
        """Run a flow locally via BotEngine.execute()."""
        from botengine.exceptions import FlowNotFoundError as EngineFlowNotFound
        from botengine.exceptions import StepExecutionError

        try:
            return await self._engine.execute(flow_id, params or None)
        except EngineFlowNotFound:
            raise FlowNotFoundError(flow_id)
        except StepExecutionError as exc:
            raise FlowExecutionError(flow_id, str(exc))

    async def _local_run_full(self, flow_id: str, params: dict[str, Any]) -> FlowResult:
        """Run a flow locally and return full FlowResult."""
        from botengine.exceptions import FlowNotFoundError as EngineFlowNotFound

        try:
            result = await self._engine.execute_full(flow_id, params or None)
        except EngineFlowNotFound:
            raise FlowNotFoundError(flow_id)

        return FlowResult(
            flow_id=result.flow_id,
            status=result.status,
            duration_ms=result.duration_ms,
            steps=[
                StepOutcome(
                    step_id=sr.step_id,
                    status=sr.status,
                    duration_ms=sr.duration_ms,
                    extracted_value=sr.extracted_value,
                    error=sr.error,
                )
                for sr in result.step_results
            ],
            returns=result.returns,
            error=None if result.status != "failed" else "Flow execution failed",
        )

    # --- Remote mode ---

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Make an HTTP request with error handling."""
        assert self._http is not None
        try:
            resp = await self._http.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise ConnectionError(self._server, str(exc))
        except httpx.TimeoutException:
            raise TimeoutError(f"Request to {self._server}{path} timed out")

        if resp.status_code == 404:
            raise FlowNotFoundError(path.split("/")[-1])
        if resp.status_code >= 400:
            detail = resp.text
            raise BotFlowClientError(f"Server error {resp.status_code}: {detail}")
        return resp

    async def _remote_list_flows(self) -> list[str]:
        """List flows via the remote server API."""
        resp = await self._request("GET", "/api/flows")
        data = resp.json()
        return [f["flow_id"] for f in data]

    async def _remote_get_flow(self, flow_id: str) -> FlowInfo:
        """Get flow info from the remote server."""
        resp = await self._request("GET", f"/api/flows/{flow_id}")
        data = resp.json()
        return FlowInfo(
            flow_id=data["flow_id"],
            site=data["site"],
            params={
                name: ParamSpec(**spec) for name, spec in data.get("params", {}).items()
            },
            returns={
                name: ReturnSpec(**spec) for name, spec in data.get("returns", {}).items()
            },
            step_count=data.get("step_count", 0),
        )

    async def _remote_run(self, flow_id: str, params: dict[str, Any]) -> dict[str, Any]:
        """Run a flow via the remote server and return its returns dict."""
        result = await self._remote_run_full(flow_id, params)
        if result.status == "failed":
            raise FlowExecutionError(flow_id, result.error or "Flow failed")
        return result.returns

    async def _remote_run_full(self, flow_id: str, params: dict[str, Any]) -> FlowResult:
        """Run a flow via the remote server, polling until complete."""
        # Start the run
        resp = await self._request(
            "POST", "/api/run-flow", json={"flow_id": flow_id, "params": params}
        )
        run_data = resp.json()
        run_id = run_data["run_id"]

        # Poll for completion
        poll_interval = 0.5
        elapsed = 0.0
        while elapsed < self._timeout:
            resp = await self._request("GET", f"/api/run-status/{run_id}")
            status_data = resp.json()

            if status_data["status"] in ("success", "failed", "cancelled"):
                return self._parse_run_status(status_data)

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            # Gradually increase poll interval (cap at 2s)
            poll_interval = min(poll_interval * 1.5, 2.0)

        raise TimeoutError(f"Flow '{flow_id}' did not complete within {self._timeout}s")

    @staticmethod
    def _parse_run_status(data: dict[str, Any]) -> FlowResult:
        """Parse a run-status response into a FlowResult."""
        steps = [
            StepOutcome(
                step_id=s.get("step_id", s.get("id", "")),
                status=s.get("status", "unknown"),
                duration_ms=s.get("duration_ms", 0.0),
                extracted_value=s.get("extracted_value"),
                error=s.get("error"),
            )
            for s in data.get("step_results", [])
        ]
        return FlowResult(
            flow_id=data["flow_id"],
            status=data["status"],
            duration_ms=data.get("duration_ms", 0.0),
            steps=steps,
            returns=data.get("returns", {}),
            error=data.get("error"),
        )
