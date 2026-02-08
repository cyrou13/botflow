"""Confidence tracking for auto-heal decisions."""

from __future__ import annotations

import json
from pathlib import Path

from botengine.logger import get_logger
from botengine.models import ConfidenceState

log = get_logger(__name__)


class ConfidenceTracker:
    """Tracks heal success/failure and adjusts auto-heal thresholds."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def get_state(self, flow_id: str) -> ConfidenceState:
        """Get current confidence state for a flow."""
        path = self._state_path(flow_id)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return ConfidenceState.model_validate(data)
        return ConfidenceState(flow_id=flow_id)

    def record_heal_success(self, flow_id: str) -> None:
        """Record a successful heal and adjust threshold."""
        state = self.get_state(flow_id)
        state.consecutive_successful_heals += 1
        state.consecutive_failed_heals = 0
        state.total_successful_heals += 1
        state.auto_threshold = self._adjust_threshold(state)
        self._save_state(state)
        log.info(
            "heal_success_recorded",
            flow_id=flow_id,
            threshold=state.auto_threshold,
            consecutive=state.consecutive_successful_heals,
        )

    def record_heal_failure(self, flow_id: str) -> None:
        """Record a failed heal and adjust threshold."""
        state = self.get_state(flow_id)
        state.consecutive_failed_heals += 1
        state.consecutive_successful_heals = 0
        state.total_failed_heals += 1
        state.auto_threshold = self._adjust_threshold(state)
        self._save_state(state)
        log.info(
            "heal_failure_recorded",
            flow_id=flow_id,
            threshold=state.auto_threshold,
            consecutive_failures=state.consecutive_failed_heals,
        )

    def should_auto_heal(self, flow_id: str, proposal_confidence: float) -> bool:
        """Check if a heal proposal should be auto-applied."""
        state = self.get_state(flow_id)
        return proposal_confidence >= state.auto_threshold

    @staticmethod
    def _adjust_threshold(state: ConfidenceState) -> float:
        """Adjust the auto-heal threshold based on track record.

        Rules:
        - Start at 100 (never auto)
        - After 5 consecutive successes: drop to 85
        - After 20 consecutive successes: drop to 70
        - After 50 consecutive successes: drop to 55
        - 1 failure: threshold += 15
        - 3 consecutive failures: reset to 100
        """
        if state.consecutive_failed_heals >= 3:
            return 100.0

        if state.consecutive_failed_heals > 0:
            return min(100.0, state.auto_threshold + 15.0)

        if state.consecutive_successful_heals >= 50:
            return 55.0
        if state.consecutive_successful_heals >= 20:
            return 70.0
        if state.consecutive_successful_heals >= 5:
            return 85.0

        return state.auto_threshold

    def _save_state(self, state: ConfidenceState) -> None:
        """Save state to disk."""
        path = self._state_path(state.flow_id)
        path.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _state_path(self, flow_id: str) -> Path:
        """Get the state file path for a flow."""
        return self.state_dir / f"{flow_id}.confidence.json"
