#!/bin/bash
set -e

echo "🎰 BotFlow — Betting Bot Example"
echo "================================="
echo ""

# Check environment variables
if [ -z "$BETCLIC_USER" ] || [ -z "$BETCLIC_PASS" ]; then
    echo "⚠️  Missing credentials. Set these environment variables:"
    echo "  export BETCLIC_USER=your_email"
    echo "  export BETCLIC_PASS=your_password"
    echo ""
    echo "Running in demo mode (will fail at login)..."
    export BETCLIC_USER="demo@example.com"
    export BETCLIC_PASS="demo_password"
fi

echo "User: $BETCLIC_USER"
echo "Heal mode: ${BOT_HEAL_MODE:-supervised}"
echo "Poll interval: ${BOT_POLL_INTERVAL:-30}s"
echo ""

python examples/betting_bot/bot.py
