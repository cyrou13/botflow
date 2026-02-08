# Dashboard — Component Instructions

## Overview
The Dashboard is a monitoring UI for BotFlow. It shows flow health, run history, and pending heal reviews.

## Stack
- FastAPI + Jinja2 templates
- Tailwind CSS via CDN
- htmx for dynamic updates (no React, no Vue)
- Dark theme throughout

## Data Sources
The dashboard reads from:
1. Flow files in the configured `flows_dir`
2. Run logs stored as JSON files in `.botflow/runs/`
3. Heal proposals stored as JSON in `.botflow/heals/`
4. Confidence state from `.botflow/confidence/`

## Routes

### `GET /` — Health Overview
- Grid of cards, one per flow
- Each card shows: flow name, status badge (🟢🟡🔴), last run time, success rate (7d), heals count
- Color coding: green (>90%), yellow (70-90%), red (<70%)
- Auto-refresh every 30s via htmx

### `GET /flow/{flow_id}` — Flow Detail
- Header: flow name, site, current heal mode, confidence threshold
- Table: last 20 runs with status, duration, steps passed/failed
- Chart area: placeholder for success rate trend (text-based is fine)
- Heal history: list of past heals with confidence, accepted/rejected

### `GET /run/{run_id}` — Run Detail
- Step-by-step breakdown: each step shows action, target, status, resolution strategy used, duration
- Failed steps highlighted in red with error message
- Screenshots if available (displayed inline)

### `GET /heals/pending` — Heal Review
- List of pending heal proposals
- Each shows: flow, step, old selectors, new selectors, confidence score, screenshots
- Buttons: ✅ Approve, ❌ Reject
- htmx POST on click, update the list

## Template Structure
- `base.html` — html head (Tailwind CDN, htmx CDN), dark body, sidebar nav, content block
- All other templates extend base.html
- Sidebar: links to Home, Flows, Pending Heals
- Keep templates under 150 lines each

## API Endpoints (JSON)
- `GET /api/health` — machine-readable health for all flows
- `POST /api/heals/{heal_id}/approve` — approve and apply a heal
- `POST /api/heals/{heal_id}/reject` — reject a heal

## Important Notes
- The dashboard is READ-ONLY for flows and runs (no editing flows here)
- Only heals can be approved/rejected
- The dashboard should work even if no runs exist yet (empty state)
- No authentication for the prototype (add later)
