"""BotFlow client exceptions."""


class BotFlowClientError(Exception):
    """Base exception for all BotFlow client errors."""


class ConnectionError(BotFlowClientError):
    """Raised when the client cannot connect to the remote server."""

    def __init__(self, url: str, detail: str = "") -> None:
        self.url = url
        msg = f"Cannot connect to {url}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class FlowNotFoundError(BotFlowClientError):
    """Raised when a requested flow does not exist."""

    def __init__(self, flow_id: str) -> None:
        self.flow_id = flow_id
        super().__init__(f"Flow not found: {flow_id}")


class FlowExecutionError(BotFlowClientError):
    """Raised when a flow execution fails."""

    def __init__(self, flow_id: str, detail: str = "") -> None:
        self.flow_id = flow_id
        self.detail = detail
        msg = f"Flow '{flow_id}' execution failed"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class TimeoutError(BotFlowClientError):
    """Raised when a flow execution or connection times out."""

    def __init__(self, detail: str = "Operation timed out") -> None:
        super().__init__(detail)
