"""BotFlow — Python client library for bot automation."""

from botflow.client import BotFlow
from botflow.exceptions import (
    BotFlowClientError,
    ConnectionError,
    FlowExecutionError,
    FlowNotFoundError,
    TimeoutError,
)
from botflow.models import FlowInfo, FlowResult, StepOutcome
from botflow.sync_client import BotFlowSync

__version__ = "0.1.0"

__all__ = [
    "BotFlow",
    "BotFlowClientError",
    "BotFlowSync",
    "ConnectionError",
    "FlowExecutionError",
    "FlowInfo",
    "FlowNotFoundError",
    "FlowResult",
    "StepOutcome",
    "TimeoutError",
    "__version__",
]
