"""BotFlow exception hierarchy."""


class BotFlowError(Exception):
    """Base exception for all BotFlow errors."""


class FlowNotFoundError(BotFlowError):
    """Raised when a flow file cannot be found."""

    def __init__(self, flow_id: str) -> None:
        self.flow_id = flow_id
        super().__init__(f"Flow not found: {flow_id}")


class FlowValidationError(BotFlowError):
    """Raised when a flow file fails schema validation."""

    def __init__(self, flow_id: str, detail: str) -> None:
        self.flow_id = flow_id
        self.detail = detail
        super().__init__(f"Flow validation error in '{flow_id}': {detail}")


class StepExecutionError(BotFlowError):
    """Raised when a flow step fails to execute."""

    def __init__(self, step_id: str, action: str, detail: str) -> None:
        self.step_id = step_id
        self.action = action
        self.detail = detail
        super().__init__(f"Step '{step_id}' ({action}) failed: {detail}")


class SelectorResolutionError(BotFlowError):
    """Raised when no resolver can find the target element."""

    def __init__(self, step_id: str, strategies_tried: list[str]) -> None:
        self.step_id = step_id
        self.strategies_tried = strategies_tried
        super().__init__(
            f"Cannot resolve element for step '{step_id}'. "
            f"Tried: {', '.join(strategies_tried)}"
        )


class HealingError(BotFlowError):
    """Raised when auto-healing fails."""

    def __init__(self, step_id: str, detail: str) -> None:
        self.step_id = step_id
        self.detail = detail
        super().__init__(f"Healing failed for step '{step_id}': {detail}")


class BrowserError(BotFlowError):
    """Raised on browser lifecycle errors."""


class ConfidenceThresholdError(BotFlowError):
    """Raised when a heal proposal doesn't meet the confidence threshold."""

    def __init__(self, score: float, threshold: float) -> None:
        self.score = score
        self.threshold = threshold
        super().__init__(
            f"Heal confidence {score:.1f} below threshold {threshold:.1f}"
        )
