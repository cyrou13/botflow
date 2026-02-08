"""Tests for confidence tracking system."""

from pathlib import Path

import pytest

from botengine.confidence import ConfidenceTracker
from botengine.models import ConfidenceState


class TestConfidenceTracker:
    def test_default_state(self, tmp_path: Path) -> None:
        tracker = ConfidenceTracker(tmp_path)
        state = tracker.get_state("test_flow")
        assert state.flow_id == "test_flow"
        assert state.auto_threshold == 100.0
        assert state.consecutive_successful_heals == 0

    def test_record_success(self, tmp_path: Path) -> None:
        tracker = ConfidenceTracker(tmp_path)
        tracker.record_heal_success("test_flow")
        state = tracker.get_state("test_flow")
        assert state.consecutive_successful_heals == 1
        assert state.total_successful_heals == 1
        assert state.consecutive_failed_heals == 0

    def test_record_failure(self, tmp_path: Path) -> None:
        tracker = ConfidenceTracker(tmp_path)
        tracker.record_heal_failure("test_flow")
        state = tracker.get_state("test_flow")
        assert state.consecutive_failed_heals == 1
        assert state.total_failed_heals == 1

    def test_success_resets_failure_counter(self, tmp_path: Path) -> None:
        tracker = ConfidenceTracker(tmp_path)
        tracker.record_heal_failure("test_flow")
        tracker.record_heal_success("test_flow")
        state = tracker.get_state("test_flow")
        assert state.consecutive_failed_heals == 0
        assert state.consecutive_successful_heals == 1

    def test_failure_resets_success_counter(self, tmp_path: Path) -> None:
        tracker = ConfidenceTracker(tmp_path)
        tracker.record_heal_success("test_flow")
        tracker.record_heal_failure("test_flow")
        state = tracker.get_state("test_flow")
        assert state.consecutive_successful_heals == 0
        assert state.consecutive_failed_heals == 1


class TestThresholdAdjustment:
    def test_5_consecutive_successes_drops_to_85(self, tmp_path: Path) -> None:
        tracker = ConfidenceTracker(tmp_path)
        for _ in range(5):
            tracker.record_heal_success("test")
        state = tracker.get_state("test")
        assert state.auto_threshold == 85.0

    def test_20_consecutive_successes_drops_to_70(self, tmp_path: Path) -> None:
        tracker = ConfidenceTracker(tmp_path)
        for _ in range(20):
            tracker.record_heal_success("test")
        state = tracker.get_state("test")
        assert state.auto_threshold == 70.0

    def test_50_consecutive_successes_drops_to_55(self, tmp_path: Path) -> None:
        tracker = ConfidenceTracker(tmp_path)
        for _ in range(50):
            tracker.record_heal_success("test")
        state = tracker.get_state("test")
        assert state.auto_threshold == 55.0

    def test_one_failure_increases_threshold(self, tmp_path: Path) -> None:
        tracker = ConfidenceTracker(tmp_path)
        # Get to 85 first
        for _ in range(5):
            tracker.record_heal_success("test")
        assert tracker.get_state("test").auto_threshold == 85.0

        tracker.record_heal_failure("test")
        state = tracker.get_state("test")
        assert state.auto_threshold == 100.0  # 85 + 15 = 100

    def test_three_consecutive_failures_resets_to_100(
        self, tmp_path: Path
    ) -> None:
        tracker = ConfidenceTracker(tmp_path)
        for _ in range(3):
            tracker.record_heal_failure("test")
        state = tracker.get_state("test")
        assert state.auto_threshold == 100.0


class TestShouldAutoHeal:
    def test_below_threshold_returns_false(self, tmp_path: Path) -> None:
        tracker = ConfidenceTracker(tmp_path)
        # Default threshold is 100
        assert tracker.should_auto_heal("test", 90) is False

    def test_meets_threshold_returns_true(self, tmp_path: Path) -> None:
        tracker = ConfidenceTracker(tmp_path)
        assert tracker.should_auto_heal("test", 100) is True

    def test_after_successes_lower_confidence_passes(
        self, tmp_path: Path
    ) -> None:
        tracker = ConfidenceTracker(tmp_path)
        for _ in range(5):
            tracker.record_heal_success("test")
        # Threshold is now 85
        assert tracker.should_auto_heal("test", 90) is True
        assert tracker.should_auto_heal("test", 80) is False

    def test_state_persists_across_instances(self, tmp_path: Path) -> None:
        tracker1 = ConfidenceTracker(tmp_path)
        for _ in range(5):
            tracker1.record_heal_success("test")

        tracker2 = ConfidenceTracker(tmp_path)
        state = tracker2.get_state("test")
        assert state.auto_threshold == 85.0
        assert state.consecutive_successful_heals == 5
