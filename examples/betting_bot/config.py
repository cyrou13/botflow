"""Configuration for the betting bot via environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class BotConfig:
    """Bot configuration loaded from environment variables."""

    betclic_user: str
    betclic_pass: str
    bankroll: float = 1000.0
    max_stake_pct: float = 0.05
    poll_interval: int = 30
    heal_mode: str = "supervised"
    anthropic_api_key: str | None = None
    flows_dir: str = "flows/examples/betclic"
    headless: bool = True

    @classmethod
    def from_env(cls) -> BotConfig:
        """Load config from environment variables."""
        return cls(
            betclic_user=os.environ.get("BETCLIC_USER", ""),
            betclic_pass=os.environ.get("BETCLIC_PASS", ""),
            bankroll=float(os.environ.get("BOT_BANKROLL", "1000")),
            max_stake_pct=float(os.environ.get("BOT_MAX_STAKE_PCT", "0.05")),
            poll_interval=int(os.environ.get("BOT_POLL_INTERVAL", "30")),
            heal_mode=os.environ.get("BOT_HEAL_MODE", "supervised"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            flows_dir=os.environ.get("BOT_FLOWS_DIR", "flows/examples/betclic"),
            headless=os.environ.get("BOT_HEADLESS", "true").lower() == "true",
        )
