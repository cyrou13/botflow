"""BotFlow Engine — Intelligent Bot Automation Framework."""

from botengine.engine import BotEngine
from botengine.exceptions import (
    BotFlowError,
    FlowNotFoundError,
    HealingError,
    SelectorResolutionError,
    StepExecutionError,
)
from botengine.models import (
    Flow,
    FlowHealth,
    FlowStep,
    HealMode,
    HealProposal,
    RunResult,
    StepResult,
    TargetSelector,
)

__version__ = "0.1.0"

__all__ = [
    "BotEngine",
    "BotFlowError",
    "Flow",
    "FlowHealth",
    "FlowNotFoundError",
    "FlowStep",
    "HealMode",
    "HealProposal",
    "HealingError",
    "RunResult",
    "SelectorResolutionError",
    "StepExecutionError",
    "StepResult",
    "TargetSelector",
    "__version__",
]
