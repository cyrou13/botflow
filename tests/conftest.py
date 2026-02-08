"""Shared test fixtures for BotFlow."""
import json
from pathlib import Path

import pytest

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"
MOCK_PAGES_DIR = FIXTURES_DIR / "mock_pages"


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def mock_pages_dir() -> Path:
    """Path to mock HTML pages."""
    return MOCK_PAGES_DIR


@pytest.fixture
def simple_form_path() -> Path:
    """Path to the simple form test page."""
    return MOCK_PAGES_DIR / "simple_form.html"


@pytest.fixture
def sample_flow_data() -> dict:
    """Load the sample flow as a dict."""
    with open(FIXTURES_DIR / "sample.flow.json") as f:
        return json.load(f)


@pytest.fixture
def sample_flow_path(tmp_path, sample_flow_data) -> Path:
    """Write sample flow to a temp directory and return the directory path."""
    flow_path = tmp_path / "test_login_and_extract.flow.json"
    with open(flow_path, "w") as f:
        json.dump(sample_flow_data, f)
    return tmp_path
