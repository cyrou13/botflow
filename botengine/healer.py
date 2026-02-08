"""Auto-healing system for broken selectors using LLM."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

from botengine.exceptions import HealingError
from botengine.logger import get_logger
from botengine.models import FlowStep, HealProposal, TargetSelector

if TYPE_CHECKING:
    import anthropic

    from botengine.flow import FlowLoader

log = get_logger(__name__)

_HEAL_TIMEOUT = 30.0


class AutoHealer:
    """LLM-powered auto-healing for broken selectors."""

    def __init__(
        self,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self._client = anthropic_client
        self._model = model

    async def propose_heal(
        self,
        step: FlowStep,
        page_screenshot: bytes,
        dom_snapshot: str,
        error: str,
    ) -> HealProposal:
        """Ask the LLM to find the element and propose new selectors."""
        if not self._client:
            raise HealingError(step.id, "No Anthropic client configured")

        old_target = (
            step.target
            if isinstance(step.target, TargetSelector)
            else TargetSelector()
        )

        prompt = self._build_heal_prompt(step, dom_snapshot, error)
        screenshot_b64 = base64.b64encode(page_screenshot).decode()

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": screenshot_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            result = self._parse_response(response.content[0].text)

            return HealProposal(
                step_id=step.id,
                old_target=old_target,
                new_target=TargetSelector(
                    css=result.get("css"),
                    xpath=result.get("xpath"),
                    text_content=result.get("text_content"),
                    aria_label=result.get("aria_label"),
                ),
                confidence_score=float(result.get("confidence", 0)),
                reasoning=result.get("reasoning", "No reasoning provided"),
            )

        except HealingError:
            raise
        except Exception as exc:
            raise HealingError(step.id, f"LLM call failed: {exc}") from exc

    async def apply_heal(
        self,
        flow_loader: FlowLoader,
        flow_id: str,
        proposal: HealProposal,
    ) -> None:
        """Apply the heal to the flow file."""
        flow = flow_loader.load(flow_id)

        for step in flow.steps:
            if step.id == proposal.step_id:
                step.target = proposal.new_target
                break
        else:
            raise HealingError(
                proposal.step_id,
                f"Step {proposal.step_id} not found in flow {flow_id}",
            )

        flow_loader.save(flow)
        log.info(
            "heal_applied",
            flow_id=flow_id,
            step_id=proposal.step_id,
            confidence=proposal.confidence_score,
        )

    @staticmethod
    def _build_heal_prompt(step: FlowStep, dom: str, error: str) -> str:
        """Build the prompt for the LLM."""
        target = (
            step.target
            if isinstance(step.target, TargetSelector)
            else TargetSelector()
        )

        return f"""You are a web automation expert. A bot step has failed because it cannot find an element.

## What the step does
{step.description or "No description"}
Action: {step.action.value}

## Previous selectors (now broken)
CSS: {target.css}
XPath: {target.xpath}
Text: {target.text_content}
Aria: {target.aria_label}
Visual description: {target.visual_anchor}

## Current page DOM (simplified)
{dom[:20000]}

## Error
{error}

## Your task
Find the element in the current DOM that corresponds to what the step is trying to interact with.
Return ONLY a JSON object (no markdown, no code fences) with:
- css: new CSS selector
- xpath: new XPath selector
- text_content: visible text of the element
- aria_label: aria label if present
- confidence: 0-100 how confident you are this is the right element
- reasoning: explain why you chose this element"""

    @staticmethod
    def _parse_response(text: str) -> dict[str, Any]:
        """Parse the LLM response as JSON."""
        # Try direct parse
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            raise HealingError("unknown", f"Could not parse LLM response: {text[:200]}")
