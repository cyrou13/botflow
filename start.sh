#!/usr/bin/env bash
# Start the BotFlow Recorder & Runner server
set -e
cd "$(dirname "$0")"

# Kill any existing instance on port 8001
lsof -i :8001 -t 2>/dev/null | xargs kill 2>/dev/null || true
sleep 1

echo "Starting BotFlow Recorder on http://localhost:8001"
uv run python -m recorder.server
