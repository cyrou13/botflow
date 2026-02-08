# Recorder — Component Instructions

## Overview
The Recorder is a web-based tool that lets users visually record automation flows by clicking through a website. It produces `.flow.json` files compatible with the BotEngine.

## Architecture
```
User's browser → FastAPI server → Playwright browser (visible)
                     ↑                      │
                     └── Injected JS ←──────┘
                         (captures clicks)
```

## How It Works
1. User starts the recorder: `python -m recorder.server`
2. A FastAPI server starts on port 8000
3. A Playwright browser opens in VISIBLE (non-headless) mode
4. User enters a URL in the recorder UI → Playwright navigates to it
5. The recorder injects `recorder.js` into the page
6. User clicks "Select Element" in the floating toolbar
7. User hovers over elements (they get highlighted)
8. User clicks an element → the JS captures all selector info
9. JS sends capture to FastAPI via `POST /api/capture-step`
10. The recorder UI panel shows the step list building up
11. User can edit steps, add params, define returns
12. User clicks "Save Flow" → `.flow.json` is written to disk

## Injected JS (`recorder.js`) Specification

### CSS Selector Generation
Generate selectors in priority order:
1. `#id` if element has a unique id
2. `[data-testid="..."]` if present
3. `[name="..."]` for form elements
4. `.class1.class2` if class combination is unique
5. `parent > tag.class:nth-child(n)` as fallback

```javascript
function generateSelector(element) {
    if (element.id) return `#${element.id}`;
    // ... cascade
}
```

### XPath Generation
```javascript
function generateXPath(element) {
    // Walk up the tree, build path
}
```

### Floating Toolbar
- Fixed position, top-right, z-index 999999
- Semi-transparent dark background
- Buttons: "🎯 Select", "📝 Extract", "⏹️ Done"
- Shows step count badge
- Draggable (optional, nice-to-have)

### Element Highlighting
- On mouseover in select mode: add a 2px solid blue outline
- On click: flash green briefly, then outline disappears
- Use `element.style.outline` (non-destructive, doesn't affect layout)

## Recorder API Endpoints

### `POST /api/start-recording`
Body: `{ "flow_id": "my_flow", "site": "example.com" }`
Creates a new recording session.

### `POST /api/capture-step`
Body:
```json
{
    "action": "click",
    "target": {
        "css": "#submit-btn",
        "xpath": "//button[@id='submit-btn']",
        "text_content": "Submit",
        "aria_label": "Submit form",
        "tag_name": "button",
        "bounding_box": { "x": 100, "y": 200, "width": 80, "height": 40 }
    },
    "url": "https://example.com/form"
}
```

### `POST /api/stop-recording`
Finalizes the flow, writes `.flow.json` to the flows directory.

### `GET /api/current-flow`
Returns the current flow being recorded (for the UI panel to display).

## UI Template (`index.html`)
- Split layout: left side = step list + editors, right side = instructions
- Dark theme (bg-gray-900, text-gray-100)
- Use htmx to poll `/api/current-flow` every second for live updates
- Each step in the list is a card showing: action icon, description, target summary
- "Save Flow" button calls `POST /api/stop-recording`

## Important Notes
- The recorder does NOT use the BotEngine to record — it uses Playwright directly
- The recorder produces the SAME Flow model that the engine consumes
- Screenshot crops for `visual_anchor` are taken during recording
- The recorder should work with any website (no site-specific code)
