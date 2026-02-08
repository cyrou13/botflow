# BotFlow — Full Auto Execution Plan

This plan is designed to be executed by Claude Code in a single `--auto` run. Each task is self-contained. Execute them IN ORDER. Run tests after each major section. Do NOT skip steps.

---

## PHASE 0 — Project Setup (estimated: 5 min)

### Task 0.1: Initialize Python project
- Create `pyproject.toml` with all dependencies (playwright, fastapi, uvicorn, pydantic, anthropic, structlog, pytest, pytest-asyncio, jinja2, httpx, python-multipart, aiofiles, pillow)
- Use `uv` if available, otherwise `pip`
- Run `uv sync` or `pip install -e ".[dev]"`
- Run `playwright install chromium`

### Task 0.2: Create base configuration
- Create `botengine/logger.py` with structlog JSON config
- Create `botengine/exceptions.py` with exception hierarchy:
  - `BotFlowError` (base)
  - `FlowNotFoundError`
  - `FlowValidationError`
  - `StepExecutionError`
  - `SelectorResolutionError`
  - `HealingError`
  - `BrowserError`
  - `ConfidenceThresholdError`

### Task 0.3: Verify setup
- Run `python -c "import playwright; print('OK')"`
- Run `python -c "import fastapi; print('OK')"`
- Run `python -c "import pydantic; print('OK')"`

---

## PHASE 1 — Data Models & Schema (estimated: 10 min)

### Task 1.1: Create Pydantic models (`botengine/models.py`)
Define ALL models used across the project:

```python
# Core flow models
class TargetSelector(BaseModel):
    css: str | None = None
    xpath: str | None = None
    text_content: str | None = None
    aria_label: str | None = None
    visual_anchor: str | None = None
    screenshot_crop: str | None = None  # base64
    dom_neighborhood: str | None = None

class PreConditions(BaseModel):
    url_pattern: str | None = None
    expected_elements: list[str] = []

class PostConditions(BaseModel):
    url_changed_to: str | None = None
    element_appears: str | None = None
    element_disappears: str | None = None
    timeout_ms: int = 5000

class FlowParam(BaseModel):
    type: Literal["string", "number", "boolean", "enum"]
    required: bool = True
    default: Any = None
    values: list[str] | None = None  # for enum type
    min: float | None = None
    max: float | None = None

class FlowReturn(BaseModel):
    type: Literal["string", "number", "boolean", "object", "array"]

class StepAction(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    EXTRACT = "extract"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    SELECT = "select"
    HOVER = "hover"
    SCROLL = "scroll"

class DynamicTarget(BaseModel):
    strategy: Literal["find_by_text", "dynamic", "css", "xpath"]
    mapping: dict[str, str] | None = None
    key: str | None = None
    text: str | None = None
    container: str | None = None

class FlowStep(BaseModel):
    id: str
    action: StepAction
    description: str | None = None
    target: TargetSelector | DynamicTarget | None = None
    url: str | None = None        # for navigate
    value: str | None = None       # for fill
    save_as: str | None = None     # for extract
    pre_conditions: PreConditions | None = None
    post_conditions: PostConditions | None = None
    timeout_ms: int = 10000
    optional: bool = False         # if True, failure doesn't stop the flow

class Flow(BaseModel):
    flow_id: str
    site: str
    version: int = 1
    params: dict[str, FlowParam] = {}
    returns: dict[str, FlowReturn] = {}
    steps: list[FlowStep]
    returns_mapping: dict[str, str] = {}

# Execution models
class StepResult(BaseModel):
    step_id: str
    status: Literal["success", "fallback", "healed", "failed", "skipped"]
    resolution_strategy: str | None = None  # which resolver worked
    duration_ms: float
    extracted_value: Any = None
    error: str | None = None
    screenshot_path: str | None = None

class RunResult(BaseModel):
    flow_id: str
    status: Literal["success", "partial", "failed"]
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    step_results: list[StepResult]
    returns: dict[str, Any] = {}
    heals_triggered: int = 0

# Healing models
class HealProposal(BaseModel):
    step_id: str
    old_target: TargetSelector
    new_target: TargetSelector
    confidence_score: float  # 0-100
    reasoning: str
    screenshot_before: str | None = None  # path
    screenshot_after: str | None = None   # path

class HealMode(str, Enum):
    OFF = "off"
    SUPERVISED = "supervised"
    AUTO = "auto"

class FlowHealth(BaseModel):
    flow_id: str
    last_run: RunResult | None = None
    success_rate_7d: float = 0.0
    heals_count_7d: int = 0
    auto_heal_threshold: float = 100.0  # starts max (all supervised)
    heal_mode: HealMode = HealMode.SUPERVISED

# Confidence tracking
class ConfidenceState(BaseModel):
    flow_id: str
    auto_threshold: float = 100.0
    consecutive_successful_heals: int = 0
    consecutive_failed_heals: int = 0
    total_successful_heals: int = 0
    total_failed_heals: int = 0
```

### Task 1.2: Create JSON Schema (`flows/schema/flow.schema.json`)
Generate a JSON Schema from the `Flow` Pydantic model. Use `Flow.model_json_schema()` and write it to file. Also create a small validation utility function.

### Task 1.3: Write model tests (`tests/unit/test_models.py`)
- Test Flow model validation with valid and invalid data
- Test that FlowStep requires appropriate fields per action type
- Test serialization/deserialization roundtrip
- Run: `pytest tests/unit/test_models.py -v`

---

## PHASE 2 — Browser Manager (estimated: 10 min)

### Task 2.1: Create browser manager (`botengine/browser.py`)
```python
class BrowserManager:
    """Manages Playwright browser lifecycle."""

    async def start(self, headless: bool = True) -> None
    async def stop(self) -> None
    async def new_context(self, cookies: list[dict] | None = None) -> BrowserContext
    async def get_page(self) -> Page
    async def screenshot(self, path: str | None = None) -> bytes
    async def get_dom_snapshot(self) -> str  # simplified DOM for LLM
    async def get_page_text(self) -> str
    @property
    def current_url(self) -> str
```

Key implementation details:
- Use `async with async_playwright() as p:` pattern
- Store browser, context, page as instance vars
- `get_dom_snapshot()` should return a SIMPLIFIED version of the DOM (strip scripts, styles, reduce depth) — this is what gets sent to the LLM for healing
- Add a method `_simplify_dom(html: str) -> str` that strips noise and keeps semantic structure
- Handle browser crashes gracefully (auto-restart)

### Task 2.2: Write browser tests (`tests/unit/test_browser.py`)
- Test start/stop lifecycle
- Test DOM simplification (provide raw HTML, check simplified output)
- Mock Playwright for unit tests

---

## PHASE 3 — Selector Resolvers (estimated: 15 min)

### Task 3.1: Create resolver interface and implementations

Base class (`botengine/resolvers/__init__.py`):
```python
class BaseResolver(ABC):
    @abstractmethod
    async def resolve(self, page: Page, target: TargetSelector) -> ElementHandle | None:
        """Try to find the element on the page. Return None if not found."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Resolver name for logging."""
```

Implement each resolver in its own file:
- `css.py` — `CSSResolver`: use `page.query_selector(target.css)`
- `xpath.py` — `XPathResolver`: use `page.query_selector(f"xpath={target.xpath}")`
- `text.py` — `TextResolver`: use `page.get_by_text(target.text_content, exact=True)`
- `aria.py` — `AriaResolver`: use `page.get_by_role()` or `page.get_by_label(target.aria_label)`
- `fuzzy.py` — `FuzzyTextResolver`: use `page.get_by_text(target.text_content, exact=False)` + scoring
- `llm_vision.py` — `LLMVisionResolver`: takes screenshot + DOM snapshot, calls Claude API, returns the best selector found. This is the most expensive resolver and should be last.

### Task 3.2: Create resolver cascade (`botengine/resolver.py`)
```python
class ResolverCascade:
    """Tries resolvers in order until one succeeds."""

    def __init__(self, resolvers: list[BaseResolver] | None = None):
        # Default order: CSS → XPath → Text → Aria → Fuzzy → LLM
        self.resolvers = resolvers or [
            CSSResolver(), XPathResolver(), TextResolver(),
            AriaResolver(), FuzzyTextResolver(), LLMVisionResolver()
        ]

    async def resolve(self, page: Page, target: TargetSelector) -> tuple[ElementHandle, str]:
        """Returns (element, resolver_name) or raises SelectorResolutionError."""
```

### Task 3.3: Write resolver tests (`tests/unit/test_resolver.py`)
- Create a test HTML fixture (`tests/fixtures/mock_pages/simple_form.html`)
- Test each resolver individually against the fixture
- Test the cascade (first resolver fails, second succeeds)
- Test full cascade failure → SelectorResolutionError
- Mock LLMVisionResolver (no real API calls)
- Run: `pytest tests/unit/test_resolver.py -v`

---

## PHASE 4 — Step Actions (estimated: 10 min)

### Task 4.1: Create action interface and implementations

Base class (`botengine/actions/__init__.py`):
```python
class BaseAction(ABC):
    @abstractmethod
    async def execute(self, page: Page, step: FlowStep, context: ExecutionContext) -> StepResult:
        """Execute the step action."""
```

`ExecutionContext` is a simple dataclass:
```python
class ExecutionContext:
    params: dict[str, Any]           # Flow params provided by user
    extracted: dict[str, Any] = {}   # Values extracted by previous steps
    screenshots_dir: Path | None = None
    resolver: ResolverCascade
```

Implement actions:
- `navigate.py` — `NavigateAction`: `page.goto(url)`, support `{{params.xxx}}` template substitution
- `click.py` — `ClickAction`: resolve target → `element.click()`, verify post_conditions
- `fill.py` — `FillAction`: resolve target → `element.fill(value)`, support template substitution
- `extract.py` — `ExtractAction`: resolve target → `element.text_content()`, store in `context.extracted[save_as]`
- `wait.py` — `WaitAction`: `page.wait_for_selector()` or `page.wait_for_url()` or `asyncio.sleep()`
- `screenshot.py` — `ScreenshotAction`: `page.screenshot()`, save to screenshots_dir

Template substitution: replace `{{params.xxx}}` and `{{extracted.xxx}}` in strings using a simple helper function.

### Task 4.2: Create action registry
```python
ACTION_REGISTRY: dict[StepAction, type[BaseAction]] = {
    StepAction.NAVIGATE: NavigateAction,
    StepAction.CLICK: ClickAction,
    # ...
}
```

### Task 4.3: Write action tests (`tests/unit/test_actions.py`)
- Test template substitution
- Test each action with mocked page
- Run: `pytest tests/unit/test_actions.py -v`

---

## PHASE 5 — Flow Engine (estimated: 10 min)

### Task 5.1: Create flow loader and runner (`botengine/flow.py`)
```python
class FlowLoader:
    """Loads and validates .flow.json files."""

    def __init__(self, flows_dir: Path):
        self.flows_dir = flows_dir
        self._cache: dict[str, Flow] = {}

    def load(self, flow_id: str) -> Flow
    def load_all(self) -> dict[str, Flow]
    def reload(self, flow_id: str) -> Flow
    def save(self, flow: Flow) -> Path  # For heal modifications

class FlowRunner:
    """Executes a flow step by step."""

    def __init__(self, browser: BrowserManager, resolver: ResolverCascade, loader: FlowLoader):
        ...

    async def run(self, flow_id: str, params: dict[str, Any] = {}) -> RunResult:
        """Execute all steps in a flow with params."""
        # 1. Load flow
        # 2. Validate params against flow.params schema
        # 3. Create ExecutionContext
        # 4. For each step:
        #    a. Check pre_conditions
        #    b. Get action from registry
        #    c. Execute action (with timeout)
        #    d. Check post_conditions
        #    e. Record StepResult
        #    f. If failed and not optional → stop or trigger heal
        # 5. Build returns from returns_mapping
        # 6. Return RunResult

    async def run_step(self, flow_id: str, step_id: str, params: dict = {}) -> StepResult:
        """Run a single step (for debugging)."""
```

### Task 5.2: Write flow tests (`tests/unit/test_flow.py`)
- Create `tests/fixtures/sample.flow.json` with a simple 3-step flow
- Test FlowLoader (load, validation, cache, reload)
- Test FlowRunner with mock browser and pages
- Test param validation
- Test template substitution in steps
- Run: `pytest tests/unit/test_flow.py -v`

---

## PHASE 6 — Auto-Healer (estimated: 15 min)

### Task 6.1: Create healer (`botengine/healer.py`)
```python
class AutoHealer:
    """LLM-powered auto-healing for broken selectors."""

    def __init__(
        self,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        ...

    async def propose_heal(
        self,
        step: FlowStep,
        page_screenshot: bytes,
        dom_snapshot: str,
        error: str
    ) -> HealProposal:
        """Ask the LLM to find the element and propose new selectors."""
        # Build a prompt with:
        # - The step description and what we're looking for
        # - The old target selectors
        # - The simplified DOM
        # - The screenshot (as base64 image)
        # - Ask for: new CSS, XPath, text_content, aria_label
        # Return HealProposal with confidence score

    async def apply_heal(
        self,
        flow_loader: FlowLoader,
        flow_id: str,
        proposal: HealProposal
    ) -> None:
        """Apply the heal to the flow file."""
        # Load flow, find step, update target, save

    def _build_heal_prompt(self, step: FlowStep, dom: str, error: str) -> str:
        """Build the prompt for the LLM."""
```

The heal prompt should be carefully crafted:
```
You are a web automation expert. A bot step has failed because it cannot find an element.

## What the step does
{step.description}
Action: {step.action}

## Previous selectors (now broken)
CSS: {target.css}
XPath: {target.xpath}
Text: {target.text_content}
Aria: {target.aria_label}
Visual description: {target.visual_anchor}

## Current page DOM (simplified)
{dom_snapshot}

## Error
{error}

## Your task
Find the element in the current DOM that corresponds to what the step is trying to interact with.
Return a JSON object with:
- css: new CSS selector
- xpath: new XPath selector
- text_content: visible text of the element
- aria_label: aria label if present
- confidence: 0-100 how confident you are this is the right element
- reasoning: explain why you chose this element
```

### Task 6.2: Create confidence system (`botengine/confidence.py`)
```python
class ConfidenceTracker:
    """Tracks heal success/failure and adjusts auto-heal thresholds."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir  # stores .confidence.json per flow

    def get_state(self, flow_id: str) -> ConfidenceState
    def record_heal_success(self, flow_id: str) -> None
    def record_heal_failure(self, flow_id: str) -> None
    def should_auto_heal(self, flow_id: str, proposal_confidence: float) -> bool
    def _adjust_threshold(self, state: ConfidenceState) -> float:
        """
        Rules:
        - Start at 100 (never auto)
        - After 5 consecutive successes: drop to 85
        - After 20 consecutive successes: drop to 70
        - 1 failure: threshold += 15
        - 3 consecutive failures: reset to 100
        """
```

### Task 6.3: Write healer tests (`tests/unit/test_healer.py`)
- Test prompt building
- Mock the Anthropic API call, return a canned response
- Test heal proposal parsing
- Test apply_heal modifies the flow correctly

### Task 6.4: Write confidence tests (`tests/unit/test_confidence.py`)
- Test threshold adjustment rules
- Test should_auto_heal at various states
- Run: `pytest tests/unit/test_healer.py tests/unit/test_confidence.py -v`

---

## PHASE 7 — Main Engine (estimated: 10 min)

### Task 7.1: Create BotEngine (`botengine/engine.py`)
```python
class BotEngine:
    """Main entry point for bot automation."""

    def __init__(
        self,
        flows_dir: str | Path,
        headless: bool = True,
        heal_mode: HealMode = HealMode.SUPERVISED,
        on_heal: Callable[[HealProposal], Awaitable[bool]] | None = None,
        anthropic_api_key: str | None = None,
        screenshots_dir: str | Path | None = None,
        log_dir: str | Path | None = None,
    ):
        ...

    # Lifecycle
    async def start(self) -> None
    async def stop(self) -> None
    async def __aenter__(self) -> "BotEngine"
    async def __aexit__(self, *args) -> None

    # Execution
    async def execute(self, flow_name: str, params: dict[str, Any] = {}) -> dict[str, Any]:
        """Execute a flow and return its declared returns."""
        # 1. Run the flow
        # 2. If step fails → attempt heal (based on mode)
        # 3. If heal approved → apply and retry the step
        # 4. Return the flow's returns mapping
        # Raises StepExecutionError if unrecoverable

    async def execute_full(self, flow_name: str, params: dict[str, Any] = {}) -> RunResult:
        """Execute and return full RunResult with all details."""

    # Status
    def flow_health(self) -> dict[str, FlowHealth]
    def list_flows(self) -> list[str]

    # Configuration
    def set_heal_mode(self, flow_name: str | None, mode: HealMode) -> None
    def set_confidence_threshold(self, flow_name: str, threshold: float) -> None
```

### Task 7.2: Create public API (`botengine/__init__.py`)
Export only:
```python
from botengine.engine import BotEngine
from botengine.models import (
    HealMode, RunResult, StepResult, HealProposal, FlowHealth,
    Flow, FlowStep, TargetSelector
)
from botengine.exceptions import (
    BotFlowError, FlowNotFoundError, StepExecutionError,
    SelectorResolutionError, HealingError
)

__version__ = "0.1.0"
```

### Task 7.3: Write engine integration test (`tests/integration/test_engine_e2e.py`)
- Create a simple HTML test page in `tests/fixtures/mock_pages/simple_form.html`
  (a form with username, password, submit button, and a success message div)
- Create a flow that fills the form and extracts the success message
- Test full engine lifecycle: start → execute → verify result → stop
- This test uses REAL Playwright (not mocked) but against a local HTML file
- Run: `pytest tests/integration/test_engine_e2e.py -v`

---

## PHASE 8 — Recorder (estimated: 15 min)

### Task 8.1: Create recorder server (`recorder/server.py`)
A FastAPI app that:
1. Opens a Playwright browser in NON-headless mode
2. Injects a recording script into every page
3. Exposes API endpoints:
   - `POST /api/start-recording` — start a new flow recording session
   - `POST /api/stop-recording` — finalize and save the flow
   - `POST /api/capture-step` — called by the injected JS when user clicks
   - `GET /api/current-flow` — returns the flow being built
   - `POST /api/navigate` — navigate to a URL
   - `GET /api/recording-status` — current recording state
4. Serves the recorder control panel UI

### Task 8.2: Create injected JS (`recorder/src/recorder.js`)
This script is injected into every page loaded in the recording browser:
- Adds a floating toolbar (fixed position, high z-index) with buttons: "Select Element", "Extract Text", "Done"
- When "Select Element" is in active mode:
  - Mouse hover highlights elements with a colored overlay
  - Click captures the element's: CSS selector (generated), XPath, text content, aria attributes, bounding box
  - Sends captured data to `POST /api/capture-step`
  - The step action is inferred: if it's an input → "fill", if it's a button/link → "click", otherwise → "extract"
- The toolbar shows the current step count and last captured element
- Use vanilla JS only (no frameworks), keep it under 300 lines

### Task 8.3: Create recorder UI (`recorder/templates/index.html`)
A simple page with:
- URL input bar + "Go" button at top
- iframe or embedded browser area (we'll use a separate browser window)
- Side panel showing:
  - Flow metadata (name, site)
  - List of recorded steps (editable)
  - Params editor (define flow params)
  - Returns editor (define what the flow returns)
  - "Save Flow" button → exports `.flow.json`
- Use Tailwind CSS via CDN, htmx for dynamic updates

### Task 8.4: Test recorder
- Start the recorder server
- Verify the API endpoints respond
- Verify the injected JS is valid
- Run: `pytest tests/integration/test_recorder.py -v`

---

## PHASE 9 — Dashboard (estimated: 10 min)

### Task 9.1: Create dashboard app (`dashboard/app.py`)
FastAPI app with routes:
- `GET /` — Overview: list all flows with health status (green/yellow/red)
- `GET /flow/{flow_id}` — Flow detail: recent runs, success rate, heal history
- `GET /run/{run_id}` — Run detail: step-by-step log with screenshots
- `GET /heals/pending` — Pending heal reviews
- `POST /heals/{heal_id}/approve` — Approve a heal
- `POST /heals/{heal_id}/reject` — Reject a heal
- `GET /api/health` — JSON health endpoint for monitoring

### Task 9.2: Create dashboard templates
Use Jinja2 + Tailwind CDN + htmx:
- `base.html` — Dark theme layout with sidebar nav
- `index.html` — Cards for each flow showing status, last run, success rate
- `flow_detail.html` — Table of recent runs + line chart of success rate
- `heal_review.html` — Side-by-side comparison: old selector vs proposed, with screenshots

Keep it functional, not fancy. The dashboard is for monitoring, not for design awards.

---

## PHASE 10 — Example Betting Bot (estimated: 10 min)

### Task 10.1: Create example flow files
Create realistic-looking flow files in `flows/examples/betclic/`:

`betclic_login.flow.json`:
- params: username (string), password (string)
- steps: navigate to betclic.fr/login, fill username, fill password, click login, wait for dashboard

`betclic_get_odds.flow.json`:
- params: match (string)
- returns: home_odds (number), draw_odds (number), away_odds (number)
- steps: navigate to live page, find match by text, extract three odds values

`betclic_place_bet.flow.json`:
- params: match (string), outcome (enum: home/draw/away), amount (number)
- returns: bet_id (string), actual_odds (number), confirmed (boolean)
- steps: navigate, find match, click outcome, extract odds, fill amount, click "Parier", wait confirmation, extract bet_id

These flows use REALISTIC selectors that would work on a typical betting site. They demonstrate all the features: params, returns, templates, pre/post conditions.

### Task 10.2: Create betting bot (`examples/betting_bot/bot.py`)
```python
"""Example betting bot using BotFlow engine."""
import asyncio
from botengine import BotEngine, HealMode

async def main():
    async with BotEngine(
        flows_dir="flows/examples/betclic",
        headless=True,
        heal_mode=HealMode.SUPERVISED,
    ) as engine:
        # Login
        await engine.execute("betclic_login", {
            "username": os.environ["BETCLIC_USER"],
            "password": os.environ["BETCLIC_PASS"],
        })

        # Main loop
        while True:
            odds = await engine.execute("betclic_get_odds", {
                "match": "PSG - OM"
            })
            decision = analyze_odds(odds)
            if decision["should_bet"]:
                result = await engine.execute("betclic_place_bet", {
                    "match": "PSG - OM",
                    "outcome": decision["outcome"],
                    "amount": decision["stake"],
                })
                print(f"Bet placed: {result}")
            await asyncio.sleep(30)

def analyze_odds(odds: dict) -> dict:
    """Simple value betting strategy."""
    # ... strategy logic ...
```

### Task 10.3: Create bot config (`examples/betting_bot/config.py`)
Simple config with environment variables for credentials, strategy params, polling interval.

### Task 10.4: Create strategy (`examples/betting_bot/strategy.py`)
A simple value betting strategy class that:
- Takes odds as input
- Computes implied probability
- Compares against a model probability (hardcoded or configurable)
- Returns bet/no-bet decision with Kelly criterion sizing

---

## PHASE 11 — Docker (estimated: 5 min)

### Task 11.1: Create Dockerfile (`docker/Dockerfile`)
```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble
# Install dependencies, copy code, set entrypoint
```

### Task 11.2: Create docker-compose (`docker/docker-compose.yml`)
Services:
- `bot` — runs the bot script
- `dashboard` — runs the dashboard on port 8080
Environment: mount flows dir, credentials via env vars

---

## PHASE 12 — Documentation (estimated: 5 min)

### Task 12.1: Write `docs/ARCHITECTURE.md`
High-level architecture doc with diagrams (text-based).

### Task 12.2: Write `docs/FLOW_FORMAT.md`
Complete reference for the `.flow.json` format with examples.

### Task 12.3: Write `docs/AUTO_HEAL.md`
Explain the auto-heal system: cascade, LLM prompts, confidence scoring, supervised vs auto modes.

---

## PHASE 13 — Final Validation (estimated: 5 min)

### Task 13.1: Run full test suite
```bash
pytest tests/ -v --tb=short
```
Fix any failures.

### Task 13.2: Run linting
```bash
python -m py_compile botengine/engine.py
python -m py_compile botengine/flow.py
# ... for all source files
```

### Task 13.3: Verify example bot
```bash
python -c "
from botengine import BotEngine, HealMode
print('BotEngine imported successfully')
print('Available classes:', dir())
"
```

### Task 13.4: Create dev setup script (`scripts/dev_setup.sh`)
```bash
#!/bin/bash
set -e
pip install -e ".[dev]"
playwright install chromium
echo "BotFlow dev environment ready!"
```

### Task 13.5: Create run example script (`scripts/run_example.sh`)
```bash
#!/bin/bash
set -e
echo "Starting BotFlow betting bot example..."
echo "Note: Set BETCLIC_USER and BETCLIC_PASS environment variables"
python examples/betting_bot/bot.py
```

---

## SUCCESS CRITERIA
After completing all phases, verify:
1. ✅ `pytest tests/unit/ -v` — all unit tests pass
2. ✅ `pytest tests/integration/ -v` — integration tests pass
3. ✅ `python -c "from botengine import BotEngine"` — imports work
4. ✅ Flow JSON files validate against the schema
5. ✅ The example bot code is syntactically correct and uses the engine API
6. ✅ Docker files are valid
7. ✅ All source files compile without errors
