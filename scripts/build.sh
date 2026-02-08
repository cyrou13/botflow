#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== BotFlow build ==="

# Clean previous builds
rm -rf dist/ build/
echo "Cleaned dist/"

# Run tests
echo "Running tests..."
uv run pytest tests/unit/ -q
echo ""

# Build wheel + sdist
echo "Building package..."
uv build

echo ""
echo "Done. Output:"
ls -lh dist/
