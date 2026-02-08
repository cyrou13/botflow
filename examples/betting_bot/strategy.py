"""Value betting strategy with Kelly criterion sizing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BetDecision:
    """Result of a betting decision."""

    should_bet: bool
    outcome: str | None = None
    stake: float = 0.0
    edge: float = 0.0
    reasoning: str = ""


class ValueBettingStrategy:
    """Simple value betting strategy.

    Detects value when estimated probability exceeds implied probability
    by a configurable margin. Uses Kelly criterion for stake sizing.
    """

    def __init__(
        self,
        bankroll: float = 1000.0,
        max_stake_pct: float = 0.05,
        edge_threshold: float = 0.05,
        model_probs: dict[str, float] | None = None,
    ) -> None:
        self.bankroll = bankroll
        self.max_stake_pct = max_stake_pct
        self.edge_threshold = edge_threshold
        # Model probabilities (in a real bot, these come from a prediction model)
        self.model_probs = model_probs or {
            "home": 0.45,
            "draw": 0.28,
            "away": 0.27,
        }

    def analyze(self, odds: dict[str, float]) -> BetDecision:
        """Analyze odds and return a betting decision.

        Args:
            odds: Dict with home_odds, draw_odds, away_odds as floats.

        Returns:
            BetDecision with should_bet, outcome, stake, etc.
        """
        home_odds = odds.get("home_odds", 0)
        draw_odds = odds.get("draw_odds", 0)
        away_odds = odds.get("away_odds", 0)

        if not all([home_odds, draw_odds, away_odds]):
            return BetDecision(
                should_bet=False, reasoning="Missing odds data"
            )

        # Convert to floats
        home_odds = float(home_odds)
        draw_odds = float(draw_odds)
        away_odds = float(away_odds)

        # Check overround (sum of implied probabilities)
        overround = (1 / home_odds) + (1 / draw_odds) + (1 / away_odds)
        if overround > 1.15:
            return BetDecision(
                should_bet=False,
                reasoning=f"Overround too high: {overround:.3f}",
            )

        # Check each outcome for value
        outcomes = {
            "home": (home_odds, self.model_probs.get("home", 0)),
            "draw": (draw_odds, self.model_probs.get("draw", 0)),
            "away": (away_odds, self.model_probs.get("away", 0)),
        }

        best_edge = 0.0
        best_outcome = None
        best_odds = 0.0

        for outcome, (decimal_odds, model_prob) in outcomes.items():
            implied_prob = 1.0 / decimal_odds
            edge = model_prob - implied_prob

            if edge > best_edge:
                best_edge = edge
                best_outcome = outcome
                best_odds = decimal_odds

        if best_outcome is None or best_edge < self.edge_threshold:
            return BetDecision(
                should_bet=False,
                reasoning=f"No value found (best edge: {best_edge:.3f})",
            )

        # Kelly criterion: f* = (bp - q) / b
        # where b = odds - 1, p = model prob, q = 1 - p
        model_prob = self.model_probs[best_outcome]
        b = best_odds - 1
        kelly_fraction = (b * model_prob - (1 - model_prob)) / b
        kelly_fraction = max(0, kelly_fraction)

        # Cap at max stake percentage
        stake_fraction = min(kelly_fraction, self.max_stake_pct)
        stake = round(self.bankroll * stake_fraction, 2)

        if stake < 1:
            return BetDecision(
                should_bet=False,
                reasoning=f"Stake too small: {stake:.2f}",
            )

        return BetDecision(
            should_bet=True,
            outcome=best_outcome,
            stake=stake,
            edge=best_edge,
            reasoning=(
                f"Value on {best_outcome} @ {best_odds:.2f} "
                f"(edge: {best_edge:.3f}, kelly: {kelly_fraction:.3f})"
            ),
        )
