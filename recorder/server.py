"""Recorder server — FastAPI app for recording automation flows.

Launches a visible Playwright browser and injects recorder.js into every page.
The injected JS sends captured steps back to this server's API.
Also provides a flow runner for testing existing flows in the browser.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from botengine.logger import get_logger
from botengine.models import Flow, HealMode

log = get_logger(__name__)

# --- Playwright browser state ---

_pw = None
_browser = None
_context = None
_page = None
_recorder_js: str | None = None

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

# --- In-memory run tracking ---

_runs: dict[str, dict[str, Any]] = {}
_run_tasks: dict[str, asyncio.Task[None]] = {}

# Load recorder.js once
_JS_PATH = Path(__file__).parent / "src" / "recorder.js"


def _get_recorder_js() -> str:
    """Load the recorder JS source."""
    global _recorder_js
    if _recorder_js is None:
        _recorder_js = _JS_PATH.read_text(encoding="utf-8")
    return _recorder_js


async def _handle_capture(data_json: str) -> str:
    """Handle a capture call from the injected JS (via expose_function).

    This runs in Python-land, bypassing CORS/CSP entirely.
    """
    import json as _json

    data = _json.loads(data_json)
    if not _recording["active"]:
        return _json.dumps({"error": "not recording"})

    step_id = f"s_{len(_recording['steps']) + 1:03d}"

    step_data: dict[str, Any] = {
        "id": step_id,
        "action": data.get("action", "click"),
        "target": {
            "css": data.get("target", {}).get("css"),
            "xpath": data.get("target", {}).get("xpath"),
            "text_content": data.get("target", {}).get("text_content"),
            "aria_label": data.get("target", {}).get("aria_label"),
            "dom_neighborhood": data.get("target", {}).get("dom_neighborhood"),
        },
    }
    if data.get("url"):
        step_data["url"] = data["url"]
    if data.get("value"):
        step_data["value"] = data["value"]

    # Auto-generate description
    tag = data.get("target", {}).get("tag_name", "element")
    text = data.get("target", {}).get("text_content", "")
    step_data["description"] = f"{data.get('action', 'click').capitalize()} {tag}"
    if text:
        step_data["description"] += f' "{text[:30]}"'

    _recording["steps"].append(step_data)
    log.info("step_captured", step_id=step_id, action=data.get("action"))
    return _json.dumps({"step_id": step_id, "step_count": len(_recording["steps"])})


async def _inject_recorder(page: Any) -> None:
    """Inject the recorder JS into a page."""
    js = _get_recorder_js()
    try:
        await page.evaluate(js)
    except Exception as exc:
        log.warning("inject_failed", error=str(exc))


async def _launch_browser() -> None:
    """Launch a visible Playwright browser."""
    global _pw, _browser, _context, _page

    from playwright.async_api import async_playwright

    _pw = await async_playwright().start()
    _browser = await _pw.chromium.launch(headless=False, slow_mo=50)
    _context = await _browser.new_context(viewport={"width": 1280, "height": 900})
    _page = await _context.new_page()

    # Expose a Python function to JS so the recorder can send captures
    # directly via window.__botflow_capture(json) — no fetch/CORS/CSP issues.
    await _page.expose_function("__botflow_capture", _handle_capture)

    await _page.goto("about:blank")

    log.info("recorder_browser_launched")


async def _close_browser() -> None:
    """Close the Playwright browser."""
    global _pw, _browser, _context, _page
    try:
        if _page and not _page.is_closed():
            await _page.close()
        if _context:
            await _context.close()
        if _browser:
            await _browser.close()
        if _pw:
            await _pw.stop()
    except Exception as exc:
        log.warning("browser_close_error", error=str(exc))
    finally:
        _page = _context = _browser = _pw = None
    log.info("recorder_browser_closed")


# --- App lifecycle ---

async def _open_ui(port: int) -> None:
    """Open the recorder UI in the default browser after a short delay."""
    await asyncio.sleep(0.5)
    webbrowser.open(f"http://localhost:{port}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Launch browser on startup, close on shutdown."""
    await _launch_browser()
    port = int(os.environ.get("RECORDER_PORT", "8001"))
    asyncio.create_task(_open_ui(port))
    yield
    # Cancel any running flow tasks
    for task in _run_tasks.values():
        task.cancel()
    _run_tasks.clear()
    _runs.clear()
    await _close_browser()


app = FastAPI(title="BotFlow Recorder", version="0.1.0", lifespan=lifespan)

# Allow cross-origin requests from any site so the injected recorder.js
# running on e.g. https://www.betclic.fr can POST back to localhost:8001.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class RunFlowRequest(BaseModel):
    flow_id: str
    params: dict[str, Any] = {}


# --- Recording API Endpoints ---


@app.post("/api/start-recording")
async def start_recording(req: StartRecordingRequest) -> dict[str, str]:
    """Start a new recording session and navigate to the site URL."""
    _recording["active"] = True
    _recording["flow_id"] = req.flow_id
    _recording["site"] = req.site
    _recording["steps"] = []
    _recording["params"] = {}
    _recording["returns"] = {}

    # Navigate the browser to the site and inject recorder
    if _page and not _page.is_closed():
        try:
            # Register recorder.js as an init script so it is automatically
            # re-injected after every navigation (including SPA route changes
            # that trigger a new document).
            js = _get_recorder_js()
            await _page.context.add_init_script(js)

            # Add a navigate step automatically
            _recording["steps"].append({
                "id": "s_001",
                "action": "navigate",
                "description": f"Navigate to {req.site}",
                "url": req.site,
            })
            await _page.goto(req.site, wait_until="domcontentloaded", timeout=30000)
            # Also inject immediately into the current page
            await _inject_recorder(_page)
        except Exception as exc:
            log.warning("navigate_failed", error=str(exc))

    log.info("recording_started", flow_id=req.flow_id, site=req.site)
    return {"status": "recording", "flow_id": req.flow_id}


@app.post("/api/navigate")
async def navigate(req: NavigateRequest) -> dict[str, str]:
    """Navigate the recording browser to a URL."""
    if not _page or _page.is_closed():
        raise HTTPException(status_code=500, detail="Browser not available")

    try:
        await _page.goto(req.url, wait_until="domcontentloaded", timeout=30000)
        if _recording["active"]:
            await _inject_recorder(_page)
            # Record as a navigate step
            step_id = f"s_{len(_recording['steps']) + 1:03d}"
            _recording["steps"].append({
                "id": step_id,
                "action": "navigate",
                "description": f"Navigate to {req.url}",
                "url": req.url,
            })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"status": "navigated", "url": req.url}


@app.post("/api/capture-step")
async def capture_step(req: CaptureStepRequest) -> dict[str, Any]:
    """Capture a step during recording (called by injected JS)."""
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
            "dom_neighborhood": req.target.get("dom_neighborhood"),
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
    params: dict = {}
    returns: dict = {}
    returns_mapping: dict = {}
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


# --- Flow Runner API Endpoints ---


@app.get("/api/flows")
async def list_flows() -> list[dict[str, Any]]:
    """List all available flows."""
    from botengine.flow import FlowLoader

    loader = FlowLoader(_flows_dir)
    flows = loader.load_all()
    result = []
    for flow_id, flow in flows.items():
        result.append({
            "flow_id": flow.flow_id,
            "site": flow.site,
            "version": flow.version,
            "step_count": len(flow.steps),
            "params": {
                name: {
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "values": p.values,
                }
                for name, p in flow.params.items()
            },
            "returns": {name: {"type": r.type} for name, r in flow.returns.items()},
        })
    return result


@app.get("/api/flows/{flow_id}")
async def get_flow(flow_id: str) -> dict[str, Any]:
    """Get a single flow's full details."""
    from botengine.flow import FlowLoader

    loader = FlowLoader(_flows_dir)
    try:
        flow = loader.load(flow_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    return {
        "flow_id": flow.flow_id,
        "site": flow.site,
        "version": flow.version,
        "step_count": len(flow.steps),
        "params": {
            name: {
                "type": p.type,
                "required": p.required,
                "default": p.default,
                "values": p.values,
            }
            for name, p in flow.params.items()
        },
        "returns": {name: {"type": r.type} for name, r in flow.returns.items()},
        "steps": [
            {
                "id": s.id,
                "action": s.action.value,
                "description": s.description,
                "url": s.url,
                "value": s.value,
                "target": s.target.model_dump(exclude_none=True) if s.target else None,
                "optional": s.optional,
                "timeout_ms": s.timeout_ms,
            }
            for s in flow.steps
        ],
    }


@app.put("/api/flows/{flow_id}")
async def update_flow(flow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Update an existing flow's JSON file."""
    # Ensure flow_id in payload matches the URL
    payload["flow_id"] = flow_id

    # Validate against Flow model
    try:
        flow = Flow.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Write to disk
    _flows_dir.mkdir(parents=True, exist_ok=True)
    path = _flows_dir / f"{flow_id}.flow.json"
    path.write_text(flow.model_dump_json(indent=2, exclude_none=True))

    log.info("flow_updated", flow_id=flow_id, path=str(path))
    return {
        "status": "saved",
        "flow_id": flow_id,
        "step_count": len(flow.steps),
    }


@app.delete("/api/flows/{flow_id:path}")
async def delete_flow(flow_id: str) -> dict[str, str]:
    """Delete a flow's JSON file."""
    # Search recursively (load_all uses rglob)
    matches = list(_flows_dir.rglob(f"{flow_id}.flow.json"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    matches[0].unlink()
    log.info("flow_deleted", flow_id=flow_id)
    return {"status": "deleted", "flow_id": flow_id}


def _render_step_description(step: Any, params: dict[str, Any]) -> str:
    """Resolve {{params.xxx}} templates in step descriptions."""
    desc = step.description or step.id
    if "{{" not in desc:
        return desc
    import re
    def replacer(match: re.Match) -> str:
        path = match.group(1).strip().split(".")
        value: Any = {"params": params}
        for part in path:
            if isinstance(value, dict):
                value = value.get(part, match.group(0))
            else:
                break
        return str(value)
    return re.sub(r"\{\{(.+?)\}\}", replacer, desc)


@app.post("/api/run-flow")
async def run_flow(req: RunFlowRequest) -> dict[str, str]:
    """Start a background flow execution."""
    from botengine.flow import FlowLoader

    # Verify the flow exists
    loader = FlowLoader(_flows_dir)
    try:
        flow = loader.load(req.flow_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Flow '{req.flow_id}' not found")

    run_id = str(uuid.uuid4())[:8]

    # Initialize run state
    _runs[run_id] = {
        "run_id": run_id,
        "flow_id": req.flow_id,
        "params": req.params,
        "status": "running",
        "started_at": datetime.now(tz=timezone.utc).isoformat(),
        "finished_at": None,
        "duration_ms": 0,
        "current_step_index": 0,
        "total_steps": len(flow.steps),
        "step_results": [],
        "returns": {},
        "error": None,
        "steps": [
            {
                "id": s.id,
                "action": s.action.value,
                "description": _render_step_description(s, req.params),
                "status": "pending",
            }
            for s in flow.steps
        ],
    }

    # Launch background task
    task = asyncio.create_task(_execute_flow_background(run_id, req.flow_id, req.params))
    _run_tasks[run_id] = task

    log.info("flow_run_started", run_id=run_id, flow_id=req.flow_id)
    return {"run_id": run_id, "status": "started"}


@app.get("/api/run-status/{run_id}")
async def run_status(run_id: str) -> dict[str, Any]:
    """Get the status of a running or completed flow execution."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return _runs[run_id]


async def _execute_flow_background(
    run_id: str, flow_id: str, params: dict[str, Any]
) -> None:
    """Execute a flow in the background, updating _runs[run_id] after each step."""
    from botengine.engine import BotEngine

    run = _runs[run_id]
    start_time = time.monotonic()

    engine: BotEngine | None = None
    try:
        engine = BotEngine(
            flows_dir=_flows_dir,
            headless=False,
            heal_mode=HealMode.OFF,
        )
        await engine.start()

        # Load the flow to iterate steps
        flow = engine._loader.load(flow_id)
        engine._runner._validate_params(flow, params or {})

        page = await engine._browser.get_page()
        from botengine.actions import ExecutionContext
        context = ExecutionContext(params=params or {}, resolver=engine._resolver)

        for i, step in enumerate(flow.steps):
            run["current_step_index"] = i
            run["steps"][i]["status"] = "running"
            step_start = time.monotonic()

            try:
                result = await engine._runner._execute_step(page, step, context)
                step_duration = (time.monotonic() - step_start) * 1000

                run["steps"][i]["status"] = result.status
                run["steps"][i]["duration_ms"] = round(step_duration, 1)
                if result.error:
                    run["steps"][i]["error"] = result.error
                if result.extracted_value is not None:
                    run["steps"][i]["extracted_value"] = result.extracted_value

                run["step_results"].append({
                    "step_id": result.step_id,
                    "status": result.status,
                    "duration_ms": round(result.duration_ms, 1),
                    "error": result.error,
                    "extracted_value": result.extracted_value,
                })

                if result.status == "failed" and not step.optional:
                    run["status"] = "failed"
                    run["error"] = result.error or f"Step {step.id} failed"
                    break
            except Exception as exc:
                step_duration = (time.monotonic() - step_start) * 1000
                run["steps"][i]["status"] = "failed"
                run["steps"][i]["duration_ms"] = round(step_duration, 1)
                run["steps"][i]["error"] = str(exc)
                run["step_results"].append({
                    "step_id": step.id,
                    "status": "failed",
                    "duration_ms": round(step_duration, 1),
                    "error": str(exc),
                })
                run["status"] = "failed"
                run["error"] = str(exc)
                break
        else:
            # All steps completed successfully
            run["status"] = "success"
            # Build returns
            returns = engine._runner._build_returns(flow, context)
            run["returns"] = returns

    except asyncio.CancelledError:
        run["status"] = "cancelled"
    except Exception as exc:
        run["status"] = "failed"
        run["error"] = str(exc)
        log.error("flow_run_error", run_id=run_id, error=str(exc))
    finally:
        run["finished_at"] = datetime.now(tz=timezone.utc).isoformat()
        run["duration_ms"] = round((time.monotonic() - start_time) * 1000, 1)
        if engine:
            try:
                await engine.stop()
            except Exception:
                pass
        _run_tasks.pop(run_id, None)
        log.info("flow_run_finished", run_id=run_id, status=run["status"])


# --- UI ---


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Serve the recorder UI."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.exists():
        return template_path.read_text()
    return "<html><body><h1>BotFlow Recorder</h1><p>Template not found.</p></body></html>"


def main() -> None:
    """Run the recorder server."""
    port = int(os.environ.get("RECORDER_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port, loop="asyncio")


if __name__ == "__main__":
    main()
