"""Tests for the recorder server API."""

import pytest
from httpx import ASGITransport, AsyncClient

from recorder.server import app


@pytest.fixture
async def client():
    """Create an async test client for the recorder API."""
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
        res = await client.post(
            "/api/start-recording",
            json={"flow_id": "test_flow", "site": "example.com"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "recording"
        assert data["flow_id"] == "test_flow"

    async def test_capture_step(self, client: AsyncClient) -> None:
        # Start recording first
        await client.post(
            "/api/start-recording",
            json={"flow_id": "test_flow", "site": "example.com"},
        )

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
        # Reset recording state
        from recorder.server import _recording
        _recording["active"] = False

        res = await client.post(
            "/api/capture-step",
            json={
                "action": "click",
                "target": {"css": "#btn"},
            },
        )
        assert res.status_code == 400

    async def test_current_flow(self, client: AsyncClient) -> None:
        await client.post(
            "/api/start-recording",
            json={"flow_id": "test_flow", "site": "example.com"},
        )
        res = await client.get("/api/current-flow")
        assert res.status_code == 200
        data = res.json()
        assert data["flow_id"] == "test_flow"
        assert data["active"] is True

    async def test_stop_recording(self, client: AsyncClient) -> None:
        await client.post(
            "/api/start-recording",
            json={"flow_id": "test_rec", "site": "test.com"},
        )
        await client.post(
            "/api/capture-step",
            json={
                "action": "click",
                "target": {"css": "#btn", "text_content": "OK"},
            },
        )
        res = await client.post("/api/stop-recording", json={})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "saved"
        assert data["step_count"] == 1

    async def test_index_returns_html(self, client: AsyncClient) -> None:
        res = await client.get("/")
        assert res.status_code == 200
        assert "BotFlow" in res.text
