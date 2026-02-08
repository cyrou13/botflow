"""Tests for the recorder server API (without browser — unit-style)."""

import pytest
from httpx import ASGITransport, AsyncClient

from recorder.server import app, _recording, _runs, _run_tasks


@pytest.fixture(autouse=True)
def reset_recording_state():
    """Reset recording state before each test."""
    _recording["active"] = False
    _recording["flow_id"] = None
    _recording["site"] = None
    _recording["steps"] = []
    _recording["params"] = {}
    _recording["returns"] = {}
    _runs.clear()
    _run_tasks.clear()
    yield


@pytest.fixture
async def client():
    """Create an async test client (no lifespan — skips browser launch)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestRecorderAPI:
    async def test_recording_status_initially_inactive(self, client: AsyncClient) -> None:
        res = await client.get("/api/recording-status")
        assert res.status_code == 200
        data = res.json()
        assert data["active"] is False

    async def test_start_recording(self, client: AsyncClient) -> None:
        # Manually set active (no browser in test mode)
        _recording["active"] = True
        _recording["flow_id"] = "test_flow"
        _recording["site"] = "example.com"
        _recording["steps"] = []

        res = await client.get("/api/recording-status")
        data = res.json()
        assert data["active"] is True
        assert data["flow_id"] == "test_flow"

    async def test_capture_step(self, client: AsyncClient) -> None:
        _recording["active"] = True
        _recording["flow_id"] = "test_flow"
        _recording["site"] = "example.com"
        _recording["steps"] = []

        res = await client.post(
            "/api/capture-step",
            json={
                "action": "click",
                "target": {
                    "css": "#btn",
                    "xpath": "//button",
                    "text_content": "Submit",
                    "aria_label": "Submit form",
                    "tag_name": "button",
                },
                "url": "https://example.com/form",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["step_id"] == "s_001"
        assert data["step_count"] == 1

    async def test_capture_step_without_recording_fails(
        self, client: AsyncClient
    ) -> None:
        res = await client.post(
            "/api/capture-step",
            json={
                "action": "click",
                "target": {"css": "#btn"},
            },
        )
        assert res.status_code == 400

    async def test_current_flow(self, client: AsyncClient) -> None:
        _recording["active"] = True
        _recording["flow_id"] = "test_flow"
        _recording["site"] = "example.com"
        _recording["steps"] = []

        res = await client.get("/api/current-flow")
        assert res.status_code == 200
        data = res.json()
        assert data["flow_id"] == "test_flow"
        assert data["active"] is True

    async def test_stop_recording(self, client: AsyncClient) -> None:
        _recording["active"] = True
        _recording["flow_id"] = "test_rec"
        _recording["site"] = "test.com"
        _recording["steps"] = [
            {
                "id": "s_001",
                "action": "click",
                "description": "Click button",
                "target": {"css": "#btn", "text_content": "OK"},
            }
        ]

        res = await client.post("/api/stop-recording", json={})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "saved"
        assert data["step_count"] == 1

    async def test_index_returns_html(self, client: AsyncClient) -> None:
        res = await client.get("/")
        assert res.status_code == 200
        assert "BotFlow" in res.text


class TestFlowRunnerAPI:
    """Tests for the flow runner API endpoints."""

    async def test_list_flows(self, client: AsyncClient) -> None:
        res = await client.get("/api/flows")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        # Should find the example flows
        flow_ids = [f["flow_id"] for f in data]
        assert "betclic_login" in flow_ids
        # Each flow should have expected fields
        login_flow = next(f for f in data if f["flow_id"] == "betclic_login")
        assert login_flow["site"] == "betclic.fr"
        assert login_flow["step_count"] == 5
        assert "username" in login_flow["params"]
        assert "password" in login_flow["params"]

    async def test_get_flow_detail(self, client: AsyncClient) -> None:
        res = await client.get("/api/flows/betclic_login")
        assert res.status_code == 200
        data = res.json()
        assert data["flow_id"] == "betclic_login"
        assert data["site"] == "betclic.fr"
        assert len(data["steps"]) == 5
        # Check step structure
        first_step = data["steps"][0]
        assert first_step["id"] == "s_001"
        assert first_step["action"] == "navigate"
        assert first_step["description"] is not None

    async def test_get_flow_detail_not_found(self, client: AsyncClient) -> None:
        res = await client.get("/api/flows/nonexistent_flow")
        assert res.status_code == 404

    async def test_run_flow_not_found(self, client: AsyncClient) -> None:
        res = await client.post(
            "/api/run-flow",
            json={"flow_id": "nonexistent_flow", "params": {}},
        )
        assert res.status_code == 404

    async def test_run_status_not_found(self, client: AsyncClient) -> None:
        res = await client.get("/api/run-status/nonexistent")
        assert res.status_code == 404

    async def test_run_status_tracking(self, client: AsyncClient) -> None:
        """Test that run state is properly tracked via _runs dict."""
        _runs["test-run"] = {
            "run_id": "test-run",
            "flow_id": "test_flow",
            "params": {},
            "status": "running",
            "started_at": "2024-01-01T00:00:00+00:00",
            "finished_at": None,
            "duration_ms": 0,
            "current_step_index": 0,
            "total_steps": 2,
            "step_results": [],
            "returns": {},
            "error": None,
            "steps": [
                {"id": "s_001", "action": "navigate", "description": "Go to site", "status": "running"},
                {"id": "s_002", "action": "click", "description": "Click btn", "status": "pending"},
            ],
        }

        res = await client.get("/api/run-status/test-run")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "running"
        assert data["total_steps"] == 2
        assert data["steps"][0]["status"] == "running"
        assert data["steps"][1]["status"] == "pending"

    async def test_index_has_tabs(self, client: AsyncClient) -> None:
        """Verify the new UI has Record and Run tabs."""
        res = await client.get("/")
        assert res.status_code == 200
        assert "tab-record" in res.text
        assert "tab-run" in res.text
        assert "switchTab" in res.text

    async def test_index_has_runner_elements(self, client: AsyncClient) -> None:
        """Verify the new UI has runner-related elements."""
        res = await client.get("/")
        assert "panel-run" in res.text
        assert "run-flow-list" in res.text
        assert "run-progress" in res.text
        assert "/api/flows" in res.text
