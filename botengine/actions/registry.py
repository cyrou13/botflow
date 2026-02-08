"""Action registry mapping step actions to implementations."""

from botengine.actions import BaseAction
from botengine.actions.click import ClickAction
from botengine.actions.extract import ExtractAction
from botengine.actions.fill import FillAction
from botengine.actions.navigate import NavigateAction
from botengine.actions.screenshot import ScreenshotAction
from botengine.actions.wait import WaitAction
from botengine.models import StepAction

ACTION_REGISTRY: dict[StepAction, type[BaseAction]] = {
    StepAction.NAVIGATE: NavigateAction,
    StepAction.CLICK: ClickAction,
    StepAction.FILL: FillAction,
    StepAction.EXTRACT: ExtractAction,
    StepAction.WAIT: WaitAction,
    StepAction.SCREENSHOT: ScreenshotAction,
}


def get_action(action: StepAction) -> BaseAction:
    """Get an action instance for the given step action type."""
    action_cls = ACTION_REGISTRY.get(action)
    if action_cls is None:
        raise ValueError(f"No action registered for: {action}")
    return action_cls()
