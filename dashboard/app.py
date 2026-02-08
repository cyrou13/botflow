"""Dashboard — FastAPI monitoring UI for BotFlow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from botengine.logger import get_logger
from botengine.models import Flow, HealMode, HealProposal

log = get_logger(__name__)

app = FastAPI(title="BotFlow Dashboard", version="0.1.0")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Configuration — set via environment or startup
FLOWS_DIR = Path("flows")
BOTFLOW_DIR = Path(".botflow")


def _load_flows() -> dict[str, dict[str, Any]]:
    """Load all flows with their metadata."""
    flows: dict[str, dict[str, Any]] = {}
    for path in FLOWS_DIR.rglob("*.flow.json"):
        try:
            data = json.loads(path.read_text())
            flow_id = data.get("flow_id", path.stem)
            flows[flow_id] = {
                "flow_id": flow_id,
                "site": data.get("site", "unknown"),
                "version": data.get("version", 1),
                "step_count": len(data.get("steps", [])),
                "path": str(path),
            }
        except Exception:
            pass
    return flows


def _load_runs(flow_id: str | None = None) -> list[dict[str, Any]]:
    """Load run history from .botflow/runs/."""
    runs_dir = BOTFLOW_DIR / "runs"
    if not runs_dir.exists():
        return []
    runs = []
    for path in sorted(runs_dir.glob("*.json"), reverse=True)[:20]:
        try:
            data = json.loads(path.read_text())
            if flow_id and data.get("flow_id") != flow_id:
                continue
            runs.append(data)
        except Exception:
            pass
    return runs


def _load_pending_heals() -> list[dict[str, Any]]:
    """Load pending heal proposals from .botflow/heals/."""
    heals_dir = BOTFLOW_DIR / "heals"
    if not heals_dir.exists():
        return []
    heals = []
    for path in sorted(heals_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
            if data.get("status") == "pending":
                data["heal_id"] = path.stem
                heals.append(data)
        except Exception:
            pass
    return heals


def _flow_health(flow_id: str) -> dict[str, Any]:
    """Compute health for a flow."""
    runs = _load_runs(flow_id)
    total = len(runs)
    successes = sum(1 for r in runs if r.get("status") == "success")
    rate = (successes / total * 100) if total > 0 else 0
    heals = sum(r.get("heals_triggered", 0) for r in runs)

    if rate >= 90:
        color = "green"
    elif rate >= 70:
        color = "yellow"
    else:
        color = "red"

    return {
        "success_rate": round(rate, 1),
        "total_runs": total,
        "heals_count": heals,
        "color": color,
        "last_run": runs[0] if runs else None,
    }


# --- HTML Routes ---


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Overview: list all flows with health status."""
    flows = _load_flows()
    flow_data = []
    for fid, finfo in flows.items():
        health = _flow_health(fid)
        flow_data.append({**finfo, **health})
    return templates.TemplateResponse(
        "index.html", {"request": request, "flows": flow_data}
    )


@app.get("/flow/{flow_id}", response_class=HTMLResponse)
async def flow_detail(request: Request, flow_id: str) -> HTMLResponse:
    """Flow detail page."""
    flows = _load_flows()
    if flow_id not in flows:
        raise HTTPException(404, "Flow not found")
    flow_info = flows[flow_id]
    health = _flow_health(flow_id)
    runs = _load_runs(flow_id)
    return templates.TemplateResponse(
        "flow_detail.html",
        {
            "request": request,
            "flow": flow_info,
            "health": health,
            "runs": runs,
        },
    )


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: str) -> HTMLResponse:
    """Run detail page."""
    run_path = BOTFLOW_DIR / "runs" / f"{run_id}.json"
    if not run_path.exists():
        raise HTTPException(404, "Run not found")
    run_data = json.loads(run_path.read_text())
    return templates.TemplateResponse(
        "run_detail.html", {"request": request, "run": run_data}
    )


@app.get("/heals/pending", response_class=HTMLResponse)
async def heals_pending(request: Request) -> HTMLResponse:
    """Pending heal reviews."""
    heals = _load_pending_heals()
    return templates.TemplateResponse(
        "heal_review.html", {"request": request, "heals": heals}
    )


# --- API Routes ---


@app.get("/api/health")
async def api_health() -> dict[str, Any]:
    """Machine-readable health for all flows."""
    flows = _load_flows()
    health = {}
    for fid in flows:
        health[fid] = _flow_health(fid)
    return {"status": "ok", "flows": health}


@app.post("/api/heals/{heal_id}/approve")
async def approve_heal(heal_id: str) -> dict[str, str]:
    """Approve a heal proposal."""
    heal_path = BOTFLOW_DIR / "heals" / f"{heal_id}.json"
    if not heal_path.exists():
        raise HTTPException(404, "Heal not found")
    data = json.loads(heal_path.read_text())
    data["status"] = "approved"
    heal_path.write_text(json.dumps(data, indent=2))
    return {"status": "approved", "heal_id": heal_id}


@app.post("/api/heals/{heal_id}/reject")
async def reject_heal(heal_id: str) -> dict[str, str]:
    """Reject a heal proposal."""
    heal_path = BOTFLOW_DIR / "heals" / f"{heal_id}.json"
    if not heal_path.exists():
        raise HTTPException(404, "Heal not found")
    data = json.loads(heal_path.read_text())
    data["status"] = "rejected"
    heal_path.write_text(json.dumps(data, indent=2))
    return {"status": "rejected", "heal_id": heal_id}


def main() -> None:
    """Run the dashboard server."""
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
