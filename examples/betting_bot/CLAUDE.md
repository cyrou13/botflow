# Examples — Component Instructions

## Overview
Example bots that demonstrate BotFlow usage. Each example is self-contained.

## Betting Bot (`betting_bot/`)
A complete example showing how to build a sports betting bot that:
1. Logs into a betting site
2. Monitors live odds in a loop
3. Makes betting decisions using a configurable strategy
4. Places bets automatically
5. Handles errors gracefully

### Key Files
- `bot.py` — main entry point, async loop
- `strategy.py` — value betting strategy with Kelly criterion
- `config.py` — configuration from environment variables

### Strategy Implementation
The strategy should implement:
- Implied probability from odds: `prob = 1 / decimal_odds`
- Overround detection: if sum of implied probs > 1.05, skip (too much margin)
- Value detection: if estimated_prob > implied_prob + margin (e.g., 0.05)
- Kelly criterion for sizing: `stake = bankroll * (estimated_prob * odds - 1) / (odds - 1)`
- Cap maximum stake at configurable % of bankroll (e.g., 5%)

### Config
All config via environment variables:
- `BETCLIC_USER`, `BETCLIC_PASS` — credentials
- `BOT_BANKROLL` — total bankroll (default 1000)
- `BOT_MAX_STAKE_PCT` — max stake % (default 0.05)
- `BOT_POLL_INTERVAL` — seconds between checks (default 30)
- `BOT_HEAL_MODE` — supervised/auto (default supervised)
- `ANTHROPIC_API_KEY` — for auto-heal (optional)
