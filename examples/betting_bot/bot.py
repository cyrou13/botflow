"""Example betting bot using BotFlow engine."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from botengine import BotEngine, HealMode, HealProposal
from examples.betting_bot.config import BotConfig
from examples.betting_bot.strategy import ValueBettingStrategy


async def on_heal_callback(proposal: HealProposal) -> bool:
    """Interactive heal approval callback."""
    print(f"\n{'='*60}")
    print(f"HEAL PROPOSAL for step: {proposal.step_id}")
    print(f"Confidence: {proposal.confidence_score}%")
    print(f"Reasoning: {proposal.reasoning}")
    print(f"Old CSS: {proposal.old_target.css}")
    print(f"New CSS: {proposal.new_target.css}")
    print(f"{'='*60}")
    response = input("Approve? (y/n): ").strip().lower()
    return response == "y"


async def main() -> None:
    """Run the betting bot."""
    config = BotConfig.from_env()

    if not config.betclic_user or not config.betclic_pass:
        print("Error: Set BETCLIC_USER and BETCLIC_PASS environment variables")
        sys.exit(1)

    heal_mode = HealMode(config.heal_mode)
    strategy = ValueBettingStrategy(
        bankroll=config.bankroll,
        max_stake_pct=config.max_stake_pct,
    )

    print(f"Starting BotFlow betting bot...")
    print(f"  Bankroll: {config.bankroll}")
    print(f"  Max stake: {config.max_stake_pct * 100}%")
    print(f"  Poll interval: {config.poll_interval}s")
    print(f"  Heal mode: {heal_mode.value}")

    async with BotEngine(
        flows_dir=config.flows_dir,
        headless=config.headless,
        heal_mode=heal_mode,
        on_heal=on_heal_callback if heal_mode == HealMode.SUPERVISED else None,
        anthropic_api_key=config.anthropic_api_key,
    ) as engine:
        # Login
        print("\nLogging in...")
        try:
            await engine.execute("betclic_login", {
                "username": config.betclic_user,
                "password": config.betclic_pass,
            })
            print("Login successful!")
        except Exception as exc:
            print(f"Login failed: {exc}")
            return

        # Main polling loop
        print("\nStarting odds monitoring loop...")
        target_match = "PSG - OM"

        while True:
            try:
                print(f"\nFetching odds for '{target_match}'...")
                odds = await engine.execute("betclic_get_odds", {
                    "match": target_match,
                })
                print(f"  Home: {odds.get('home_odds')}")
                print(f"  Draw: {odds.get('draw_odds')}")
                print(f"  Away: {odds.get('away_odds')}")

                decision = strategy.analyze(odds)
                print(f"  Decision: {decision.reasoning}")

                if decision.should_bet:
                    print(f"\n  Placing bet: {decision.outcome} @ {decision.stake}")
                    result = await engine.execute("betclic_place_bet", {
                        "match": target_match,
                        "outcome": decision.outcome,
                        "amount": decision.stake,
                    })
                    print(f"  Bet placed! ID: {result.get('bet_id')}")
                    print(f"  Confirmed odds: {result.get('actual_odds')}")

                    # Update bankroll
                    strategy.bankroll -= decision.stake
                    print(f"  Remaining bankroll: {strategy.bankroll:.2f}")

            except KeyboardInterrupt:
                print("\nStopping bot...")
                break
            except Exception as exc:
                print(f"  Error: {exc}")

            print(f"\nWaiting {config.poll_interval}s...")
            await asyncio.sleep(config.poll_interval)


if __name__ == "__main__":
    asyncio.run(main())
