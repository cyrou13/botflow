# BotFlow — Intelligent Bot Automation Framework

## Vision
BotFlow is a Python framework for creating, running, and auto-maintaining web automation bots. It combines Playwright-powered browser control with LLM-based auto-healing to create bots that survive website redesigns.

## Architecture Overview

```
User Code (bot logic) → BotEngine API → Flow Engine → Playwright → Browser
                                            ↓
                                     Auto-Heal (LLM)
```

### Three Layers
1. **BotEngine API** (`botengine/`) — Python library exposing `execute(flow_name, params)` → structured results
2. **Flow Engine** (`botengine/flow.py`, `botengine/resolver.py`) — Loads `.flow.json` files, resolves selectors via cascade strategy, runs steps
3. **Browser Runtime** (`botengine/browser.py`) — Playwright wrapper managing browser instances, sessions, cookies

### Supporting Components
4. **Recorder** (`recorder/`) — Lightweight web UI (Flask + injected JS) for point-and-click flow recording
5. **Dashboard** (`dashboard/`) — FastAPI + htmx monitoring UI for runs, heals, health status
6. **Auto-Healer** (`botengine/healer.py`) — LLM-powered selector repair with confidence scoring

## Tech Stack (STRICT — do not deviate)
- **Python 3.11+** — all backend code
- **Playwright (Python)** — browser automation (NOT Selenium, NOT Puppeteer)
- **FastAPI** — for dashboard and recorder server
- **htmx + Tailwind CSS** — for dashboard and recorder UI (NO React, NO heavy JS frameworks)
- **Pydantic v2** — all data models, flow schema validation
- **Claude API (anthropic SDK)** — for auto-heal LLM calls
- **pytest + pytest-asyncio** — testing
- **Docker** — deployment runtime
- **SQLite** — run logs and heal history (NO Postgres for prototype)

## Code Conventions

### Python Style
- Use `async/await` throughout — the engine is fully async
- Type hints on ALL functions (params + return)
- Pydantic models for ALL data structures (no raw dicts)
- Use `structlog` for logging (structured JSON logs)
- No classes with more than 200 lines — split into mixins or modules
- Use `Path` from pathlib, never string concatenation for paths
- Docstrings: Google style, concise
- Error handling: custom exception hierarchy rooted in `BotFlowError`

### File Organization
- One class per file when the class is substantial (>50 lines)
- Group related small utilities in a single file
- `__init__.py` files export the public API only
- Private functions prefixed with `_`

### Testing
- Every public method has at least one test
- Use `pytest.fixture` for browser and engine setup
- Mock Playwright for unit tests, real browser for integration
- Test files mirror source structure: `botengine/resolver.py` → `tests/unit/test_resolver.py`

### Flow Files
- Format: JSON with `.flow.json` extension
- Validated against JSON Schema in `flows/schema/flow.schema.json`
- All flows have `params` and `returns` typed definitions
- Steps reference targets with multiple resolution strategies

## Key Design Decisions
1. **Flows are declarative JSON, NOT code** — this allows the recorder to generate them, the engine to introspect them, and the healer to modify them
2. **Selector resolution is a cascade** — CSS → XPath → text → aria → fuzzy text → LLM vision (each step is fast, LLM is last resort)
3. **Auto-heal modifies the .flow.json file** — fixes are persistent, not runtime patches
4. **Confidence scoring gates auto-heal** — new bots start supervised, earn autonomy
5. **The engine is a library, not a framework** — user code calls the engine, not the other way around
6. **Recorder is separate from runtime** — record on desktop, deploy headless in Docker

## Project Structure
```
botflow/
├── CLAUDE.md                          # This file
├── PLAN.md                            # Full execution plan for Claude Code
├── pyproject.toml                     # Python project config (uv/pip)
├── botengine/                         # Core library
│   ├── CLAUDE.md                      # Component-specific instructions
│   ├── __init__.py                    # Public API exports
│   ├── engine.py                      # BotEngine main class
│   ├── flow.py                        # Flow loader and runner
│   ├── browser.py                     # Playwright browser manager
│   ├── resolver.py                    # Selector resolution cascade
│   ├── healer.py                      # Auto-heal orchestrator
│   ├── confidence.py                  # Confidence scoring system
│   ├── models.py                      # All Pydantic models
│   ├── exceptions.py                  # Exception hierarchy
│   ├── logger.py                      # Structured logging setup
│   ├── actions/                       # Step action implementations
│   │   ├── __init__.py
│   │   ├── navigate.py
│   │   ├── click.py
│   │   ├── fill.py
│   │   ├── extract.py
│   │   ├── wait.py
│   │   └── screenshot.py
│   └── resolvers/                     # Selector resolution strategies
│       ├── __init__.py
│       ├── css.py
│       ├── xpath.py
│       ├── text.py
│       ├── aria.py
│       ├── fuzzy.py
│       └── llm_vision.py
├── recorder/                          # Flow recording tool
│   ├── CLAUDE.md
│   ├── server.py                      # Flask/FastAPI server with proxy
│   ├── injector.py                    # JS injection for click capture
│   ├── src/
│   │   └── recorder.js               # Injected JS for element selection
│   ├── public/
│   │   └── recorder_ui.html           # Recording control panel
│   └── templates/
│       └── index.html                 # Main recorder page
├── dashboard/                         # Monitoring dashboard
│   ├── CLAUDE.md
│   ├── app.py                         # FastAPI app
│   ├── src/
│   │   └── dashboard.js               # htmx interactions
│   └── templates/
│       ├── base.html
│       ├── index.html                 # Overview / health
│       ├── flow_detail.html           # Single flow view
│       ├── run_detail.html            # Single run view
│       └── heal_review.html           # Heal approval UI
├── flows/                             # Flow definitions
│   ├── schema/
│   │   └── flow.schema.json           # JSON Schema for .flow.json
│   └── examples/
│       └── betclic/                   # Example flows for betting
│           ├── betclic_login.flow.json
│           ├── betclic_get_odds.flow.json
│           └── betclic_place_bet.flow.json
├── examples/
│   └── betting_bot/
│       ├── CLAUDE.md
│       ├── bot.py                     # Main bot script
│       ├── strategy.py                # Betting strategy logic
│       └── config.py                  # Bot configuration
├── tests/
│   ├── CLAUDE.md
│   ├── conftest.py                    # Shared fixtures
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_resolver.py
│   │   ├── test_flow.py
│   │   ├── test_healer.py
│   │   ├── test_confidence.py
│   │   └── test_actions.py
│   ├── integration/
│   │   ├── test_engine_e2e.py
│   │   └── test_recorder.py
│   └── fixtures/
│       ├── sample.flow.json
│       └── mock_pages/
│           └── simple_form.html
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── FLOW_FORMAT.md
│   └── AUTO_HEAL.md
└── scripts/
    ├── dev_setup.sh
    └── run_example.sh
```

## Commands Reference
```bash
# Development
uv sync                              # Install dependencies
pytest                                # Run all tests
pytest tests/unit                     # Unit tests only
python -m recorder.server             # Start recorder
python -m dashboard.app               # Start dashboard
python examples/betting_bot/bot.py    # Run example bot

# Docker
docker compose -f docker/docker-compose.yml up
```

## Critical Reminders for Claude Code
1. **READ the component CLAUDE.md before working on that component**
2. **Run tests after each component is built** — `pytest tests/unit/test_<component>.py`
3. **The flow.schema.json is the source of truth** — build it first, validate against it
4. **Keep LLM costs minimal** — the auto-heal LLM call is the LAST resort in the cascade
5. **No network calls in unit tests** — mock everything
6. **The prototype must work end-to-end** — a user should be able to record a flow and run it
