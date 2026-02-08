# BotEngine Core — Component Instructions

## Overview
This is the core Python library for BotFlow. It provides the `BotEngine` class that users import to run their bots.

## Module Dependency Order (build in this order)
1. `exceptions.py` — no dependencies
2. `logger.py` — no dependencies
3. `models.py` — depends on nothing internal
4. `resolvers/` — depends on models
5. `resolver.py` — depends on resolvers/
6. `actions/` — depends on models, resolver
7. `browser.py` — depends on models
8. `flow.py` — depends on models, browser, resolver, actions
9. `confidence.py` — depends on models
10. `healer.py` — depends on models, confidence, flow (for saving)
11. `engine.py` — depends on everything above

## Critical Implementation Details

### Browser Manager
- Use `async_playwright()` context manager
- Store `_playwright`, `_browser`, `_context`, `_page` as private attrs
- `get_dom_snapshot()` must strip `<script>`, `<style>`, `<svg>`, comments, and inline styles
- Keep only: tag name, id, class, text content, aria-*, data-*, href, type, name, placeholder
- Limit DOM depth to 6 levels
- Max DOM size: 50KB (truncate if larger, keeping first 25KB + last 25KB)

### Resolver Cascade
- Each resolver gets max 2 seconds per attempt
- If a resolver returns multiple matches, prefer: visible > above fold > larger
- LLMVisionResolver should ONLY be instantiated if an API key is available
- If no API key, the cascade stops at FuzzyTextResolver

### Template Substitution
Use a simple regex-based approach:
```python
import re
def render_template(template: str, context: dict) -> str:
    def replacer(match):
        path = match.group(1).strip()
        parts = path.split(".")
        value = context
        for part in parts:
            value = value[part]
        return str(value)
    return re.sub(r"\{\{(.+?)\}\}", replacer, template)
```

### Flow Runner Error Handling
- If a step fails and `step.optional` is True → skip and continue
- If a step fails and `step.optional` is False → attempt heal (if mode != OFF)
- If heal succeeds → retry the step ONCE
- If heal fails or mode is OFF → raise StepExecutionError
- Always capture screenshots on failure for debugging

### Auto-Healer LLM Call
- Use claude-sonnet-4-20250514 (fast + good enough for selector finding)
- Send: simplified DOM (text) + screenshot (base64 image) + step description
- Parse response as JSON
- Timeout: 30 seconds
- If API call fails → treat as heal failure, don't crash

### Confidence System
- State stored as JSON files in a `.botflow/` directory alongside flows
- Thread-safe: use file locking or atomic writes
- Threshold adjustments:
  - 5 consecutive successful heals: threshold = 85
  - 20 consecutive successful heals: threshold = 70
  - 50 consecutive successful heals: threshold = 55
  - 1 failure: threshold += 15
  - 3 consecutive failures: reset to 100

## Testing Strategy
- Unit tests mock Playwright entirely (use `unittest.mock.AsyncMock`)
- Create a `MockPage` fixture that returns predictable elements
- For resolver tests, use the HTML fixture in `tests/fixtures/mock_pages/`
- For healer tests, mock the Anthropic client
- Integration tests use real Playwright against local HTML files
