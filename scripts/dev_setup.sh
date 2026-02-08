#!/bin/bash
set -e

echo "🚀 Setting up BotFlow development environment..."

# Check Python version
python3 --version 2>/dev/null || { echo "❌ Python 3 required"; exit 1; }

# Install dependencies
if command -v uv &> /dev/null; then
    echo "📦 Installing with uv..."
    uv sync
else
    echo "📦 Installing with pip..."
    pip install -e ".[dev]"
fi

# Install Playwright browsers
echo "🌐 Installing Playwright browsers..."
playwright install chromium

# Create runtime directories
mkdir -p .botflow/runs .botflow/heals .botflow/confidence .botflow/screenshots

echo ""
echo "✅ BotFlow dev environment ready!"
echo ""
echo "Quick start:"
echo "  pytest                              # Run tests"
echo "  python -m recorder.server           # Start recorder"
echo "  python -m dashboard.app             # Start dashboard"
echo "  python examples/betting_bot/bot.py  # Run example bot"
