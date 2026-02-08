# BotFlow Architecture

## Overview

BotFlow is a three-layer framework for building resilient web automation bots.

## Layer 1: BotEngine API

The public-facing Python library. Users import `BotEngine` and call `execute(flow_name, params)`. They never interact with Playwright, selectors, or DOM directly.

```python
async with BotEngine(flows_dir="./flows") as engine:
    result = await engine.execute("my_flow", {"key": "value"})
```

## Layer 2: Flow Engine

Loads `.flow.json` files, validates parameters, executes steps sequentially. Each step goes through:
1. Pre-condition check (URL, expected elements)
2. Target resolution via the resolver cascade
3. Action execution (click, fill, extract, etc.)
4. Post-condition check (URL change, element appears)

If a step fails, the engine triggers the auto-heal system (if enabled).

## Layer 3: Browser Runtime

Playwright manages the actual browser. Runs headless in production, visible during recording. Handles: navigation, screenshots, DOM snapshots, cookie/session persistence.

## Auto-Heal System

When a selector breaks:
1. **Cascade resolution** tries fallback strategies (CSS → XPath → text → aria → fuzzy)
2. If all fail, **LLM Vision** gets a screenshot + simplified DOM and proposes new selectors
3. **Confidence scoring** decides whether to auto-apply or require human review
4. Approved fixes are persisted back to the `.flow.json` file

## Data Flow

```
.flow.json → FlowLoader → FlowRunner → StepActions → Playwright
                                ↓ (on failure)
                           AutoHealer → Claude API → HealProposal
                                ↓
                        ConfidenceTracker → auto-apply or queue for review
```

## Deployment

Bots run in Docker containers with headless Chromium. The dashboard runs as a separate service for monitoring. Flows are mounted as volumes for easy updates.
