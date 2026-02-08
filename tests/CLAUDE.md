# Tests — Component Instructions

## Overview
All tests for BotFlow. Uses pytest + pytest-asyncio.

## Structure
- `conftest.py` — shared fixtures (mock browser, mock page, mock engine, temp dirs)
- `unit/` — isolated tests, no real browser, no network
- `integration/` — real Playwright tests against local HTML files
- `fixtures/` — test data (sample flows, mock HTML pages)

## Conventions
- Every test file starts with `test_`
- Every test function starts with `test_`
- Use `@pytest.mark.asyncio` for all async tests
- Use descriptive test names: `test_resolver_cascade_falls_back_to_text_when_css_fails`
- Group related tests in classes: `class TestResolverCascade:`
- Use `tmp_path` fixture for any file I/O

## Key Fixtures (in conftest.py)

```python
@pytest.fixture
def sample_flow() -> Flow:
    """A minimal valid flow for testing."""

@pytest.fixture
def sample_flow_path(tmp_path, sample_flow) -> Path:
    """Write sample flow to a temp directory and return path."""

@pytest.fixture
def mock_page():
    """AsyncMock of a Playwright Page."""

@pytest.fixture
def mock_browser_manager(mock_page):
    """AsyncMock of BrowserManager that returns mock_page."""

@pytest.fixture
def resolver_cascade():
    """ResolverCascade with only deterministic resolvers (no LLM)."""

@pytest.fixture
async def real_browser():
    """Real Playwright browser for integration tests."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        yield browser
        await browser.close()
```

## Mock HTML Page (`fixtures/mock_pages/simple_form.html`)
A self-contained HTML file with:
- A login form: username input, password input, submit button
- Various elements with different selector strategies (id, class, aria, text)
- A hidden success div that appears after "submit"
- Enough DOM complexity to test resolver cascade

## Running Tests
```bash
# All tests
pytest -v

# Unit only (fast)
pytest tests/unit/ -v

# Integration only (needs Playwright)
pytest tests/integration/ -v

# Specific component
pytest tests/unit/test_resolver.py -v

# With coverage
pytest --cov=botengine tests/
```
