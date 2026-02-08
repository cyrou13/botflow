"""Synchronous wrapper around BotFlow for scripts."""

from __future__ import annotations

import asyncio
from typing import Any

from botflow.client import BotFlow
from botflow.models import FlowInfo, FlowResult


class BotFlowSync:
    """Synchronous wrapper around BotFlow for use in scripts.

    Runs each async call via ``asyncio.run()`` in a fresh event loop.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs
        self._client: BotFlow | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._start()

    def _start(self) -> None:
        """Create event loop and start the async client."""
        self._loop = asyncio.new_event_loop()
        self._client = BotFlow(**self._kwargs)
        self._loop.run_until_complete(self._client.start())

    def _run(self, coro: Any) -> Any:
        """Run a coroutine on the internal event loop."""
        assert self._loop is not None
        return self._loop.run_until_complete(coro)

    def list_flows(self) -> list[str]:
        """List all available flow IDs."""
        return self._run(self._client.list_flows())

    def get_flow(self, flow_id: str) -> FlowInfo:
        """Get metadata for a specific flow."""
        return self._run(self._client.get_flow(flow_id))

    def run(self, flow_id: str, **params: Any) -> dict[str, Any]:
        """Execute a flow and return its declared returns dict."""
        return self._run(self._client.run(flow_id, **params))

    def run_full(self, flow_id: str, **params: Any) -> FlowResult:
        """Execute a flow and return the full FlowResult."""
        return self._run(self._client.run_full(flow_id, **params))

    def close(self) -> None:
        """Shut down the client and event loop."""
        if self._client and self._loop:
            self._loop.run_until_complete(self._client.stop())
            self._loop.close()
            self._loop = None
            self._client = None

    def __enter__(self) -> BotFlowSync:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
