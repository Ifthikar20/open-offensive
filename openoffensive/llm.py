"""Optional LLM brain — drives one agent with Claude via a manual tool-use loop.

This is what turns OpenOffensive from a scripted demo into a real agent: instead
of following a fixed methodology, the agent asks a model what to do next, the
model calls tools (real HTTP probes, report_finding, load_skill…), and the loop
feeds the results back until the model calls ``finish``. Every tool call still
flows through the shared registry, so it is logged and scope-guarded exactly like
scripted mode.

The ``anthropic`` SDK is imported lazily so the package installs and runs with no
dependencies; LLM mode needs ``pip install 'openoffensive[llm]'`` and an
``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import logging
from typing import Any

from .tools import ToolContext, anthropic_schemas, execute

logger = logging.getLogger(__name__)

# Input / output USD per 1M tokens, for the run's cost meter.
_PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}


class LLMUnavailable(RuntimeError):
    """Raised when LLM mode is requested but cannot run (no SDK or no key)."""


def llm_available(settings: Any) -> tuple[bool, str]:
    """(usable, reason) — whether a real model call can be made right now."""
    if not getattr(settings, "api_key_present", False):
        return False, "ANTHROPIC_API_KEY is not set"
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False, "the 'anthropic' package is not installed (pip install 'openoffensive[llm]')"
    return True, ""


def _cost(model: str, usage: Any) -> float:
    pin, pout = _PRICES.get(model, _PRICES["claude-opus-5"])
    it = getattr(usage, "input_tokens", 0) or 0
    ot = getattr(usage, "output_tokens", 0) or 0
    return it / 1_000_000 * pin + ot / 1_000_000 * pout


def run_agent_llm(ctx: ToolContext, *, system_prompt: str, task: str,
                  tool_names: list[str], settings: Any) -> None:
    """Run one agent to completion under model control. Raises LLMUnavailable if
    the SDK/key are missing; other model errors surface as exceptions to the
    caller (which marks the agent stopped)."""
    usable, reason = llm_available(settings)
    if not usable:
        raise LLMUnavailable(reason)

    import anthropic

    client = anthropic.Anthropic()
    model = settings.model
    tools = anthropic_schemas(tool_names)
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

    for _step in range(settings.max_steps):
        resp = client.messages.create(
            model=model,
            max_tokens=settings.max_tokens,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )
        ctx.coord.bill(ctx.agent, turns=1, cost=_cost(model, resp.usage))

        if getattr(resp, "stop_reason", None) == "refusal":
            ctx.coord.emit("error", ctx.agent, "model declined this request (refusal)")
            return

        messages.append({"role": "assistant", "content": resp.content})

        tool_results: list[dict[str, Any]] = []
        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "text" and block.text.strip():
                ctx.coord.emit("think", ctx.agent, block.text.strip())
            elif btype == "tool_use":
                observation = execute(ctx, block.name, dict(block.input or {}))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": observation,
                })

        if ctx.finished:
            return
        if not tool_results:
            # Model ended its turn without calling a tool — nudge once, then stop.
            if getattr(resp, "stop_reason", None) != "tool_use":
                messages.append({"role": "user", "content":
                                 "Continue testing with a tool call, or call finish "
                                 "if your assigned work is complete."})
                continue
        messages.append({"role": "user", "content": tool_results})

    ctx.coord.emit("think", ctx.agent, f"reached the {settings.max_steps}-step budget; wrapping up")
