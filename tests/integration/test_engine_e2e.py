"""End-to-end integration test using real Playwright against local HTML."""

import json
from pathlib import Path

import pytest

from botengine import BotEngine, HealMode


@pytest.fixture
def flow_dir(tmp_path: Path, simple_form_path: Path) -> Path:
    """Create a flow dir with a test flow pointing to the local HTML file."""
    flow_data = {
        "flow_id": "test_local_form",
        "site": "localhost",
        "version": 1,
        "params": {
            "username": {"type": "string", "required": True},
            "password": {"type": "string", "required": True},
        },
        "returns": {
            "welcome_text": {"type": "string"},
        },
        "steps": [
            {
                "id": "s_navigate",
                "action": "navigate",
                "description": "Open the local test page",
                "url": f"file://{simple_form_path}",
            },
            {
                "id": "s_fill_user",
                "action": "fill",
                "description": "Fill username",
                "target": {
                    "css": "#username",
                    "aria_label": "Username input",
                },
                "value": "{{params.username}}",
            },
            {
                "id": "s_fill_pass",
                "action": "fill",
                "description": "Fill password",
                "target": {
                    "css": "#password",
                    "aria_label": "Password input",
                },
                "value": "{{params.password}}",
            },
            {
                "id": "s_click_login",
                "action": "click",
                "description": "Click login button",
                "target": {
                    "css": "#login-btn",
                    "text_content": "Login",
                },
                "post_conditions": {
                    "element_appears": "#dashboard-section",
                    "timeout_ms": 5000,
                },
            },
            {
                "id": "s_extract",
                "action": "extract",
                "description": "Extract welcome message",
                "target": {
                    "css": "#user-display",
                },
                "save_as": "welcome_text",
            },
        ],
        "returns_mapping": {
            "welcome_text": "{{extracted.welcome_text}}",
        },
    }
    flow_file = tmp_path / "test_local_form.flow.json"
    flow_file.write_text(json.dumps(flow_data))
    return tmp_path


async def test_full_engine_lifecycle(flow_dir: Path) -> None:
    """Test full engine lifecycle: start -> execute -> verify -> stop."""
    async with BotEngine(
        flows_dir=flow_dir,
        headless=True,
        heal_mode=HealMode.OFF,
    ) as engine:
        # Verify flow listing
        flows = engine.list_flows()
        assert "test_local_form" in flows

        # Execute the flow
        result = await engine.execute(
            "test_local_form",
            params={"username": "testuser", "password": "secret123"},
        )

        # Verify returns
        assert "welcome_text" in result
        assert result["welcome_text"] == "testuser"


async def test_full_result_details(flow_dir: Path) -> None:
    """Test execute_full returns detailed RunResult."""
    async with BotEngine(
        flows_dir=flow_dir,
        headless=True,
        heal_mode=HealMode.OFF,
    ) as engine:
        result = await engine.execute_full(
            "test_local_form",
            params={"username": "testuser", "password": "secret123"},
        )

        assert result.status == "success"
        assert result.flow_id == "test_local_form"
        assert len(result.step_results) == 5
        assert all(r.status == "success" for r in result.step_results)
        assert result.duration_ms > 0
