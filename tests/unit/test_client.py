"""Tests for the BotFlow client library."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from botflow.client import BotFlow
from botflow.exceptions import (
    BotFlowClientError,
    ConnectionError,
    FlowExecutionError,
    FlowNotFoundError,
    TimeoutError,
)
from botflow.models import FlowInfo, FlowResult, StepOutcome
from botflow.sync_client import BotFlowSync


# --- Construction tests ---


class TestBotFlowConstruction:
    """Test BotFlow constructor validation."""

    def test_requires_flows_dir_or_server(self):
        with pytest.raises(BotFlowClientError, match="Provide either"):
            BotFlow()

    def test_rejects_both_flows_dir_and_server(self):
        with pytest.raises(BotFlowClientError, match="not both"):
            BotFlow(flows_dir="./flows", server="http://localhost:8001")

    def test_local_mode_constructor(self):
        client = BotFlow(flows_dir="./flows")
        assert client._flows_dir == Path("./flows")
        assert client._server is None

    def test_remote_mode_constructor(self):
        client = BotFlow(server="http://localhost:8001")
        assert client._server == "http://localhost:8001"
        assert client._flows_dir is None

    def test_server_url_trailing_slash_stripped(self):
        client = BotFlow(server="http://localhost:8001/")
        assert client._server == "http://localhost:8001"

    def test_defaults(self):
        client = BotFlow(flows_dir="./flows")
        assert client._headless is True
        assert client._heal_mode == "off"
        assert client._timeout == 120.0


# --- Local mode tests ---


class TestLocalMode:
    """Test BotFlow in local mode (embedded BotEngine)."""

    @pytest.fixture
    def mock_engine(self):
        engine = AsyncMock()
        # list_flows is sync on BotEngine, so use a plain MagicMock
        engine.list_flows = MagicMock(return_value=["login", "extract_odds"])
        engine.execute.return_value = {"home": "Braga", "away": "Rio Ave"}
        engine.execute_full.return_value = MagicMock(
            flow_id="extract_odds",
            status="success",
            duration_ms=1500.0,
            step_results=[
                MagicMock(
                    step_id="s_001",
                    status="success",
                    duration_ms=500.0,
                    extracted_value=None,
                    error=None,
                ),
                MagicMock(
                    step_id="s_002",
                    status="success",
                    duration_ms=1000.0,
                    extracted_value="Braga",
                    error=None,
                ),
            ],
            returns={"home": "Braga", "away": "Rio Ave"},
        )
        # Mock the _loader for get_flow
        mock_flow = MagicMock()
        mock_flow.flow_id = "extract_odds"
        mock_flow.site = "https://example.com"
        mock_flow.params = {}
        mock_flow.returns = {}
        mock_flow.steps = [MagicMock(), MagicMock()]
        engine._loader = MagicMock()
        engine._loader.load.return_value = mock_flow
        return engine

    async def test_list_flows(self, mock_engine):
        client = BotFlow(flows_dir="./flows")
        client._engine = mock_engine
        result = await client.list_flows()
        assert result == ["login", "extract_odds"]
        mock_engine.list_flows.assert_called_once()

    async def test_run_delegates_to_engine(self, mock_engine):
        client = BotFlow(flows_dir="./flows")
        client._engine = mock_engine
        result = await client.run("extract_odds", url="https://example.com")
        assert result == {"home": "Braga", "away": "Rio Ave"}
        mock_engine.execute.assert_called_once_with(
            "extract_odds", {"url": "https://example.com"}
        )

    async def test_run_with_no_params(self, mock_engine):
        client = BotFlow(flows_dir="./flows")
        client._engine = mock_engine
        await client.run("extract_odds")
        mock_engine.execute.assert_called_once_with("extract_odds", None)

    async def test_run_full_returns_flow_result(self, mock_engine):
        client = BotFlow(flows_dir="./flows")
        client._engine = mock_engine
        result = await client.run_full("extract_odds", url="https://example.com")
        assert isinstance(result, FlowResult)
        assert result.flow_id == "extract_odds"
        assert result.status == "success"
        assert len(result.steps) == 2
        assert result.returns == {"home": "Braga", "away": "Rio Ave"}

    async def test_get_flow_returns_flow_info(self, mock_engine):
        client = BotFlow(flows_dir="./flows")
        client._engine = mock_engine
        info = await client.get_flow("extract_odds")
        assert isinstance(info, FlowInfo)
        assert info.flow_id == "extract_odds"
        assert info.step_count == 2

    async def test_run_flow_not_found(self, mock_engine):
        from botengine.exceptions import FlowNotFoundError as EngineFlowNotFound

        mock_engine.execute.side_effect = EngineFlowNotFound("missing_flow")
        client = BotFlow(flows_dir="./flows")
        client._engine = mock_engine
        with pytest.raises(FlowNotFoundError, match="missing_flow"):
            await client.run("missing_flow")

    async def test_run_execution_error(self, mock_engine):
        from botengine.exceptions import StepExecutionError

        mock_engine.execute.side_effect = StepExecutionError(
            "s_001", "click", "Element not found"
        )
        client = BotFlow(flows_dir="./flows")
        client._engine = mock_engine
        with pytest.raises(FlowExecutionError, match="extract_odds"):
            await client.run("extract_odds")

    async def test_context_manager(self):
        with patch("botflow.client.BotFlow._start_local", new_callable=AsyncMock) as mock_start:
            async with BotFlow(flows_dir="./flows") as client:
                mock_start.assert_called_once()
                assert client._engine is not None or mock_start.called


# --- Remote mode tests ---


class TestRemoteMode:
    """Test BotFlow in remote mode (HTTP API)."""

    @pytest.fixture
    def mock_http(self):
        return AsyncMock(spec=httpx.AsyncClient)

    def _make_response(self, status_code: int = 200, json_data: dict | list | None = None):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.text = str(json_data)
        return resp

    async def test_list_flows_remote(self, mock_http):
        mock_http.request.return_value = self._make_response(
            json_data=[
                {"flow_id": "login", "site": "example.com"},
                {"flow_id": "extract", "site": "example.com"},
            ]
        )
        client = BotFlow(server="http://localhost:8001")
        client._http = mock_http
        result = await client.list_flows()
        assert result == ["login", "extract"]
        mock_http.request.assert_called_once_with("GET", "/api/flows")

    async def test_get_flow_remote(self, mock_http):
        mock_http.request.return_value = self._make_response(
            json_data={
                "flow_id": "login",
                "site": "https://example.com",
                "step_count": 3,
                "params": {"username": {"type": "string", "required": True}},
                "returns": {"token": {"type": "string"}},
            }
        )
        client = BotFlow(server="http://localhost:8001")
        client._http = mock_http
        info = await client.get_flow("login")
        assert isinstance(info, FlowInfo)
        assert info.flow_id == "login"
        assert info.step_count == 3
        assert "username" in info.params

    async def test_run_remote_polls_until_done(self, mock_http):
        # First call: POST /api/run-flow → returns run_id
        start_resp = self._make_response(json_data={"run_id": "abc123", "status": "started"})
        # Second call: GET /api/run-status/abc123 → running
        running_resp = self._make_response(
            json_data={"flow_id": "login", "status": "running", "step_results": []}
        )
        # Third call: GET /api/run-status/abc123 → success
        done_resp = self._make_response(
            json_data={
                "flow_id": "login",
                "status": "success",
                "duration_ms": 1200.0,
                "step_results": [
                    {"step_id": "s_001", "status": "success", "duration_ms": 600.0}
                ],
                "returns": {"token": "abc"},
            }
        )
        mock_http.request.side_effect = [start_resp, running_resp, done_resp]

        client = BotFlow(server="http://localhost:8001")
        client._http = mock_http
        result = await client.run("login", username="test")
        assert result == {"token": "abc"}

    async def test_run_full_remote(self, mock_http):
        start_resp = self._make_response(json_data={"run_id": "abc123", "status": "started"})
        done_resp = self._make_response(
            json_data={
                "flow_id": "login",
                "status": "success",
                "duration_ms": 1200.0,
                "step_results": [
                    {
                        "step_id": "s_001",
                        "status": "success",
                        "duration_ms": 600.0,
                        "extracted_value": "hello",
                    }
                ],
                "returns": {"token": "abc"},
            }
        )
        mock_http.request.side_effect = [start_resp, done_resp]

        client = BotFlow(server="http://localhost:8001")
        client._http = mock_http
        result = await client.run_full("login", username="test")
        assert isinstance(result, FlowResult)
        assert result.status == "success"
        assert len(result.steps) == 1
        assert result.steps[0].extracted_value == "hello"

    async def test_run_remote_flow_failed(self, mock_http):
        start_resp = self._make_response(json_data={"run_id": "abc123", "status": "started"})
        done_resp = self._make_response(
            json_data={
                "flow_id": "login",
                "status": "failed",
                "duration_ms": 500.0,
                "step_results": [],
                "returns": {},
                "error": "Element not found",
            }
        )
        mock_http.request.side_effect = [start_resp, done_resp]

        client = BotFlow(server="http://localhost:8001")
        client._http = mock_http
        with pytest.raises(FlowExecutionError, match="login"):
            await client.run("login")

    async def test_connection_error(self, mock_http):
        mock_http.request.side_effect = httpx.ConnectError("Connection refused")

        client = BotFlow(server="http://localhost:9999")
        client._http = mock_http
        with pytest.raises(ConnectionError, match="localhost:9999"):
            await client.list_flows()

    async def test_timeout_error(self, mock_http):
        mock_http.request.side_effect = httpx.TimeoutException("timed out")

        client = BotFlow(server="http://localhost:8001")
        client._http = mock_http
        with pytest.raises(TimeoutError, match="timed out"):
            await client.list_flows()

    async def test_flow_not_found_404(self, mock_http):
        mock_http.request.return_value = self._make_response(status_code=404)

        client = BotFlow(server="http://localhost:8001")
        client._http = mock_http
        with pytest.raises(FlowNotFoundError):
            await client.get_flow("nonexistent")

    async def test_server_error_raises_client_error(self, mock_http):
        mock_http.request.return_value = self._make_response(
            status_code=500, json_data={"detail": "Internal error"}
        )

        client = BotFlow(server="http://localhost:8001")
        client._http = mock_http
        with pytest.raises(BotFlowClientError, match="500"):
            await client.list_flows()

    async def test_run_remote_timeout(self, mock_http):
        """Test that polling times out if the run never completes."""
        start_resp = self._make_response(json_data={"run_id": "abc", "status": "started"})
        running_resp = self._make_response(
            json_data={"flow_id": "login", "status": "running", "step_results": []}
        )
        # Always return running
        mock_http.request.side_effect = [start_resp] + [running_resp] * 100

        client = BotFlow(server="http://localhost:8001", timeout=1.0)
        client._http = mock_http
        with pytest.raises(TimeoutError, match="did not complete"):
            await client.run("login")


# --- Sync wrapper tests ---


class TestBotFlowSync:
    """Test the synchronous BotFlowSync wrapper."""

    def test_sync_list_flows(self):
        with patch("botflow.sync_client.BotFlow") as MockBotFlow:
            mock_client = AsyncMock()
            mock_client.list_flows.return_value = ["flow_a", "flow_b"]
            mock_client.start = AsyncMock()
            mock_client.stop = AsyncMock()
            MockBotFlow.return_value = mock_client

            bot = BotFlowSync(server="http://localhost:8001")
            result = bot.list_flows()
            assert result == ["flow_a", "flow_b"]
            bot.close()

    def test_sync_run(self):
        with patch("botflow.sync_client.BotFlow") as MockBotFlow:
            mock_client = AsyncMock()
            mock_client.run.return_value = {"data": "value"}
            mock_client.start = AsyncMock()
            mock_client.stop = AsyncMock()
            MockBotFlow.return_value = mock_client

            bot = BotFlowSync(server="http://localhost:8001")
            result = bot.run("my_flow", url="https://example.com")
            assert result == {"data": "value"}
            bot.close()

    def test_sync_run_full(self):
        with patch("botflow.sync_client.BotFlow") as MockBotFlow:
            mock_client = AsyncMock()
            flow_result = FlowResult(
                flow_id="test", status="success", duration_ms=100.0, returns={"x": 1}
            )
            mock_client.run_full.return_value = flow_result
            mock_client.start = AsyncMock()
            mock_client.stop = AsyncMock()
            MockBotFlow.return_value = mock_client

            bot = BotFlowSync(server="http://localhost:8001")
            result = bot.run_full("test")
            assert isinstance(result, FlowResult)
            assert result.status == "success"
            bot.close()

    def test_sync_context_manager(self):
        with patch("botflow.sync_client.BotFlow") as MockBotFlow:
            mock_client = AsyncMock()
            mock_client.list_flows.return_value = ["a"]
            mock_client.start = AsyncMock()
            mock_client.stop = AsyncMock()
            MockBotFlow.return_value = mock_client

            with BotFlowSync(server="http://localhost:8001") as bot:
                assert bot.list_flows() == ["a"]
            # stop should have been called
            mock_client.stop.assert_called_once()

    def test_sync_get_flow(self):
        with patch("botflow.sync_client.BotFlow") as MockBotFlow:
            mock_client = AsyncMock()
            mock_client.get_flow.return_value = FlowInfo(
                flow_id="test", site="example.com", step_count=2
            )
            mock_client.start = AsyncMock()
            mock_client.stop = AsyncMock()
            MockBotFlow.return_value = mock_client

            bot = BotFlowSync(server="http://localhost:8001")
            info = bot.get_flow("test")
            assert info.flow_id == "test"
            assert info.step_count == 2
            bot.close()


# --- Model tests ---


class TestModels:
    """Test client models."""

    def test_flow_info_defaults(self):
        info = FlowInfo(flow_id="test", site="example.com")
        assert info.step_count == 0
        assert info.params == {}
        assert info.returns == {}

    def test_step_outcome(self):
        outcome = StepOutcome(step_id="s_001", status="success", duration_ms=123.4)
        assert outcome.error is None
        assert outcome.extracted_value is None

    def test_flow_result(self):
        result = FlowResult(
            flow_id="test",
            status="success",
            duration_ms=1000.0,
            steps=[
                StepOutcome(step_id="s_001", status="success", duration_ms=500.0),
                StepOutcome(step_id="s_002", status="failed", duration_ms=500.0, error="oops"),
            ],
            returns={"key": "value"},
        )
        assert len(result.steps) == 2
        assert result.steps[1].error == "oops"
        assert result.returns == {"key": "value"}

    def test_flow_result_defaults(self):
        result = FlowResult(flow_id="test", status="success")
        assert result.duration_ms == 0.0
        assert result.steps == []
        assert result.returns == {}
        assert result.error is None
