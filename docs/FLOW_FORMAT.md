# Flow Format Reference

## File Format

Flows are JSON files with the `.flow.json` extension. They must conform to `flows/schema/flow.schema.json`.

## Structure

```json
{
  "flow_id": "unique_identifier",
  "site": "example.com",
  "version": 1,
  "params": { ... },
  "returns": { ... },
  "steps": [ ... ],
  "returns_mapping": { ... }
}
```

## Fields

### `flow_id` (required)
Unique identifier for the flow. Used in `engine.execute(flow_id, ...)`.

### `site` (required)
The website this flow operates on. Informational only.

### `version` (required)
Integer version number. Incremented by auto-heal when it modifies the flow.

### `params`
Input parameters the flow accepts. Map of name → param definition:
- `type`: "string" | "number" | "boolean" | "enum"
- `required`: boolean (default true)
- `default`: default value if not provided
- `values`: list of valid values (for enum type)
- `min`, `max`: numeric bounds (for number type)

### `returns`
Output values the flow produces. Map of name → return definition:
- `type`: "string" | "number" | "boolean" | "object" | "array"

### `steps`
Ordered list of actions to execute. Each step has:
- `id`: unique step identifier (e.g., "s_001")
- `action`: "navigate" | "click" | "fill" | "extract" | "wait" | "screenshot" | "select" | "hover" | "scroll"
- `description`: human-readable description of what this step does
- `target`: selector information (see Target Types below)
- `value`: value to fill (for fill action), supports templates
- `url`: URL to navigate to (for navigate action)
- `save_as`: variable name to store extracted value (for extract action)
- `pre_conditions`: conditions that must be true before executing
- `post_conditions`: conditions that must be true after executing
- `timeout_ms`: max time to wait (default 10000)
- `optional`: if true, failure doesn't stop the flow

### `returns_mapping`
Maps flow return names to extracted values using template syntax.

## Target Types

### TargetSelector (standard)
Multiple selector strategies for the same element:
```json
{
  "css": "#my-button",
  "xpath": "//button[@id='my-button']",
  "text_content": "Submit",
  "aria_label": "Submit form",
  "visual_anchor": "blue button at bottom of form",
  "dom_neighborhood": "inside form#checkout"
}
```

### DynamicTarget (parameterized)
For elements that depend on flow params:
```json
{
  "strategy": "dynamic",
  "mapping": {
    "home": ".outcome-home",
    "away": ".outcome-away"
  },
  "key": "{{params.outcome}}"
}
```

Or text-based search:
```json
{
  "strategy": "find_by_text",
  "text": "{{params.match}}",
  "container": ".events-list"
}
```

## Template Syntax

Use `{{params.xxx}}` for flow parameters and `{{extracted.xxx}}` for values extracted by previous steps.

## Example

See `flows/examples/betclic/` for complete real-world examples.
