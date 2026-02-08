"""Recorder server — FastAPI app for recording automation flows."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from botengine.logger import get_logger
from botengine.models import Flow, FlowParam, FlowReturn, FlowStep, StepAction, TargetSelector

log = get_logger(__name__)

app = FastAPI(title="BotFlow Recorder", version="0.1.0")

# --- In-memory recording state ---

_recording: dict[str, Any] = {
    "active": False,
    "flow_id": None,
    "site": None,
    "steps": [],
    "params": {},
    "returns": {},
}

_flows_dir = Path("flows")


# --- Request/Response models ---


class StartRecordingRequest(BaseModel):
    flow_id: str
    site: str


class CaptureStepRequest(BaseModel):
    action: str
    target: dict[str, Any]
    url: str | None = None
    value: str | None = None


class StopRecordingRequest(BaseModel):
    params: dict[str, dict[str, Any]] | None = None
    returns: dict[str, dict[str, Any]] | None = None
    returns_mapping: dict[str, str] | None = None


class NavigateRequest(BaseModel):
    url: str


class RecordingStatus(BaseModel):
    active: bool
    flow_id: str | None
    site: str | None
    step_count: int


# --- API Endpoints ---


@app.post("/api/start-recording")
async def start_recording(req: StartRecordingRequest) -> dict[str, str]:
    """Start a new flow recording session."""
    _recording["active"] = True
    _recording["flow_id"] = req.flow_id
    _recording["site"] = req.site
    _recording["steps"] = []
    _recording["params"] = {}
    _recording["returns"] = {}
    log.info("recording_started", flow_id=req.flow_id, site=req.site)
    return {"status": "recording", "flow_id": req.flow_id}


@app.post("/api/capture-step")
async def capture_step(req: CaptureStepRequest) -> dict[str, Any]:
    """Capture a step during recording."""
    if not _recording["active"]:
        raise HTTPException(status_code=400, detail="Not recording")

    step_id = f"s_{len(_recording['steps']) + 1:03d}"

    step_data: dict[str, Any] = {
        "id": step_id,
        "action": req.action,
        "target": {
            "css": req.target.get("css"),
            "xpath": req.target.get("xpath"),
            "text_content": req.target.get("text_content"),
            "aria_label": req.target.get("aria_label"),
        },
    }
    if req.url:
        step_data["url"] = req.url
    if req.value:
        step_data["value"] = req.value

    # Auto-generate description
    tag = req.target.get("tag_name", "element")
    text = req.target.get("text_content", "")
    step_data["description"] = f"{req.action.capitalize()} {tag}"
    if text:
        step_data["description"] += f' "{text[:30]}"'

    _recording["steps"].append(step_data)
    log.info("step_captured", step_id=step_id, action=req.action)
    return {"step_id": step_id, "step_count": len(_recording["steps"])}


@app.post("/api/stop-recording")
async def stop_recording(
    req: StopRecordingRequest | None = None,
) -> dict[str, Any]:
    """Finalize and save the flow."""
    if not _recording["active"]:
        raise HTTPException(status_code=400, detail="Not recording")

    flow_id = _recording["flow_id"]
    site = _recording["site"]
    steps = _recording["steps"]

    if not steps:
        raise HTTPException(status_code=400, detail="No steps recorded")

    # Build flow
    params = {}
    returns = {}
    returns_mapping = {}
    if req:
        if req.params:
            params = req.params
        if req.returns:
            returns = req.returns
        if req.returns_mapping:
            returns_mapping = req.returns_mapping

    flow_data = {
        "flow_id": flow_id,
        "site": site,
        "version": 1,
        "params": params,
        "returns": returns,
        "steps": steps,
        "returns_mapping": returns_mapping,
    }

    # Validate
    flow = Flow.model_validate(flow_data)

    # Save
    _flows_dir.mkdir(parents=True, exist_ok=True)
    path = _flows_dir / f"{flow_id}.flow.json"
    path.write_text(flow.model_dump_json(indent=2, exclude_none=True))

    # Reset state
    _recording["active"] = False
    _recording["steps"] = []

    log.info("recording_saved", flow_id=flow_id, path=str(path))
    return {"status": "saved", "path": str(path), "step_count": len(steps)}


@app.get("/api/current-flow")
async def get_current_flow() -> dict[str, Any]:
    """Return the flow being built."""
    return {
        "flow_id": _recording["flow_id"],
        "site": _recording["site"],
        "steps": _recording["steps"],
        "active": _recording["active"],
    }


@app.get("/api/recording-status")
async def recording_status() -> RecordingStatus:
    """Get current recording state."""
    return RecordingStatus(
        active=_recording["active"],
        flow_id=_recording["flow_id"],
        site=_recording["site"],
        step_count=len(_recording["steps"]),
    )


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Serve the recorder UI."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.exists():
        return template_path.read_text()
    return "<html><body><h1>BotFlow Recorder</h1><p>Template not found.</p></body></html>"


def main() -> None:
    """Run the recorder server."""
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
