# Auto-Heal System

## Overview

BotFlow's auto-heal system repairs broken selectors when websites change. It combines fast deterministic fallbacks with LLM-powered visual analysis as a last resort.

## Resolution Cascade

When a step's primary selector fails, BotFlow tries alternatives in order:

| Priority | Resolver | Speed | Cost |
|----------|----------|-------|------|
| 1 | CSS Selector | <10ms | Free |
| 2 | XPath | <10ms | Free |
| 3 | Text Content (exact) | <20ms | Free |
| 4 | Aria Label | <20ms | Free |
| 5 | Text Content (fuzzy) | <50ms | Free |
| 6 | LLM Vision | 2-5s | ~$0.01 |

Steps 1-5 resolve 90%+ of breakages (selector renamed but text/aria unchanged). Step 6 handles visual redesigns where the element moved or was restructured.

## LLM Vision Resolver

Sends Claude API a request with:
- Screenshot of the current page (base64 image)
- Simplified DOM (stripped of scripts, styles, limited depth)
- Description of what element we're looking for
- Previous selectors that worked

Claude analyzes the page visually and structurally, then returns new selectors with a confidence score.

## Heal Modes

### OFF
No healing. Steps fail immediately if the primary selector cascade (1-5) fails. LLM is never called.

### SUPERVISED (default)
The full cascade runs including LLM. If a fix is proposed, it's queued for human review in the dashboard. The bot pauses or skips the step.

### AUTO
The full cascade runs. If the confidence score exceeds the flow's threshold, the fix is applied automatically. Otherwise, it falls back to supervised mode.

## Confidence Scoring

Each flow has an auto-heal threshold that starts at 100 (never auto-heal) and decreases as trust builds:

- **New flow**: threshold = 100 (everything requires review)
- **After 5 successful heals**: threshold = 85
- **After 20 successful heals**: threshold = 70
- **After 50 successful heals**: threshold = 55
- **1 failed heal**: threshold += 15
- **3 consecutive failed heals**: reset to 100

A heal is "successful" if:
1. The proposed fix was applied (manually or auto)
2. The step and subsequent steps pass on the next run

## Fix Persistence

When a heal is approved, BotFlow:
1. Updates the step's `target` in the `.flow.json` file
2. Increments the flow's `version` number
3. Logs the change in `.botflow/heals/`
4. Updates the confidence state in `.botflow/confidence/`

## Cost Optimization

- LLM calls only happen after all free resolvers fail
- DOM snapshots are compressed (stripped, depth-limited, max 50KB)
- Screenshots are resized to 1280x720 max before sending
- One LLM call per broken step (not per retry)
- Expected cost: $0.01-0.03 per heal attempt
