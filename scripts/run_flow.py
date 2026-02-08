#!/usr/bin/env python3
"""Interactive flow runner — test flows with a visible browser."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from botengine import BotEngine, HealMode


FLOWS_DIR = Path(__file__).resolve().parents[1] / "flows"


def discover_flows(base: Path) -> list[Path]:
    """Find all .flow.json files recursively."""
    return sorted(base.rglob("*.flow.json"))


def pick_flow(flows: list[Path]) -> Path:
    """Let the user choose a flow from the list."""
    print("\nAvailable flows:")
    for i, f in enumerate(flows, 1):
        rel = f.relative_to(FLOWS_DIR)
        with open(f) as fh:
            data = json.load(fh)
        desc = data.get("steps", [{}])[0].get("description", "")
        print(f"  {i}. {rel}  — {desc}")

    while True:
        choice = input(f"\nSelect flow [1-{len(flows)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(flows):
            return flows[int(choice) - 1]
        print("Invalid choice, try again.")


def collect_params(flow_path: Path) -> dict:
    """Ask the user for each required param."""
    with open(flow_path) as fh:
        data = json.load(fh)

    params_spec = data.get("params", {})
    if not params_spec:
        return {}

    print("\nParameters:")
    params: dict = {}
    for name, spec in params_spec.items():
        required = spec.get("required", False)
        ptype = spec.get("type", "string")
        suffix = " (required)" if required else " (optional, Enter to skip)"
        value = input(f"  {name} [{ptype}]{suffix}: ").strip()
        if value:
            params[name] = value
        elif required:
            print(f"  ⚠  {name} is required!")
            value = input(f"  {name} [{ptype}]: ").strip()
            params[name] = value

    return params


async def run(flow_path: Path, params: dict) -> None:
    """Execute the flow with a visible browser."""
    flow_id = flow_path.stem.replace(".flow", "")

    # Determine which flows_dir contains this file
    flows_dir = flow_path.parent

    print(f"\n▶ Running flow: {flow_id}")
    print(f"  Flows dir:    {flows_dir}")
    print(f"  Params:       {params}")
    print(f"  Browser:      visible (headless=False)")
    print()

    async with BotEngine(
        flows_dir=flows_dir,
        headless=False,
        heal_mode=HealMode.OFF,
    ) as engine:
        try:
            result = await engine.execute_full(flow_id, params or None)

            print(f"\n{'='*60}")
            print(f"  Status: {result.status}")
            print(f"  Duration: {result.duration_ms:.0f}ms")
            print(f"  Steps:")
            for sr in result.step_results:
                icon = "✓" if sr.status == "success" else "✗"
                print(f"    {icon} {sr.step_id} [{sr.status}] {sr.duration_ms:.0f}ms")
                if sr.error:
                    print(f"      Error: {sr.error}")
                if sr.extracted_value:
                    print(f"      Extracted: {sr.extracted_value}")
            if result.returns:
                print(f"  Returns: {json.dumps(result.returns, indent=4)}")
            print(f"{'='*60}")

        except Exception as exc:
            print(f"\n✗ Flow failed: {exc}")

        input("\nPress Enter to close the browser...")


def main() -> None:
    flows = discover_flows(FLOWS_DIR)
    if not flows:
        print(f"No .flow.json files found in {FLOWS_DIR}")
        sys.exit(1)

    flow_path = pick_flow(flows)
    params = collect_params(flow_path)
    asyncio.run(run(flow_path, params))


if __name__ == "__main__":
    main()
