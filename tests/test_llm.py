"""The optional LLM brain.

Two halves:
  * ``llm_available`` reports honestly when the SDK/key are missing (the
    ``anthropic`` package is genuinely NOT installed in this environment);
  * ``run_agent_llm`` drives a full tool-use loop against a MOCKED anthropic
    SDK injected into ``sys.modules``, executing real tools INSIDE an injected
    :class:`FakeSandbox` and terminating when the model calls ``finish``.
"""

from __future__ import annotations

import copy
import sys
import types

import pytest

from conftest import build_settings, make_agent

from openoffensive import Coordinator, Settings
from openoffensive import llm as llm_mod
from openoffensive.llm import LLMUnavailable
from openoffensive.sandbox.fake import FakeSandbox
from openoffensive.tools import ToolContext


# ---------------------------------------------------------------------------
# minimal-but-correct fakes for the anthropic SDK objects
# ---------------------------------------------------------------------------
class FakeBlock:
    def __init__(self, type, *, text=None, name=None, input=None, id=None):
        self.type = type
        self.text = text
        self.name = name
        self.input = input
        self.id = id


class FakeUsage:
    def __init__(self, input_tokens=100, output_tokens=50):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class FakeResponse:
    def __init__(self, content, stop_reason="tool_use"):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = FakeUsage()


def install_fake_anthropic(monkeypatch, responses):
    """Inject a fake ``anthropic`` module whose client replays ``responses``."""
    calls: list[dict] = []

    class FakeMessages:
        def create(self, **kwargs):
            # Snapshot the args: run_agent_llm keeps mutating the same messages
            # list in place, so a live reference would show only the final state.
            calls.append(copy.deepcopy(kwargs))
            assert responses, "fake anthropic ran out of scripted responses"
            return responses.pop(0)

    class FakeAnthropic:
        def __init__(self, *args, **kwargs):
            self.messages = FakeMessages()

    module = types.ModuleType("anthropic")
    module.Anthropic = FakeAnthropic
    module.calls = calls
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return module


def _llm_ctx(coord, tmp_path, **over):
    settings = build_settings(tmp_path, api_key_present=True, **over)
    sandbox = FakeSandbox(default=("TOOL OUTPUT", 0))
    ctx = ToolContext(coord, make_agent(), settings, sandbox, coord.target)
    return ctx, settings, sandbox


# ---------------------------------------------------------------------------
# llm_available — honest about missing key / missing SDK
# ---------------------------------------------------------------------------
def test_llm_available_false_without_key():
    ok, reason = llm_mod.llm_available(Settings(api_key_present=False))
    assert ok is False
    assert "ANTHROPIC_API_KEY" in reason


def test_llm_available_false_without_package(monkeypatch):
    # Guarantee the package is absent regardless of any test ordering.
    monkeypatch.delitem(sys.modules, "anthropic", raising=False)
    ok, reason = llm_mod.llm_available(Settings(api_key_present=True))
    assert ok is False
    assert "anthropic" in reason
    assert "not installed" in reason


def test_llm_available_true_with_key_and_fake_sdk(monkeypatch):
    install_fake_anthropic(monkeypatch, [])
    ok, reason = llm_mod.llm_available(Settings(api_key_present=True))
    assert ok is True
    assert reason == ""


# ---------------------------------------------------------------------------
# preflight_model — the shared "is the model actually reachable" probe
# ---------------------------------------------------------------------------
def test_preflight_model_reports_no_key():
    ok, msg = llm_mod.preflight_model(Settings(api_key_present=False))
    assert ok is False
    assert "ANTHROPIC_API_KEY" in msg


def test_preflight_model_ok_with_reachable_model(monkeypatch):
    install_fake_anthropic(monkeypatch, [FakeResponse([], stop_reason="end_turn")])
    ok, msg = llm_mod.preflight_model(Settings(api_key_present=True, model="claude-probe"))
    assert ok is True
    assert "claude-probe" in msg


def test_preflight_model_surfaces_connection_cause(monkeypatch):
    err = RuntimeError("Connection error.")
    err.__cause__ = OSError("SSL: CERTIFICATE_VERIFY_FAILED")

    class _Msgs:
        def create(self, **kw):
            raise err

    class _Client:
        messages = _Msgs()

        def __init__(self, *a, **k):
            pass

    module = types.ModuleType("anthropic")
    module.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", module)

    ok, msg = llm_mod.preflight_model(Settings(api_key_present=True, model="claude-probe"))
    assert ok is False
    assert "Connection error" in msg
    assert "CERTIFICATE_VERIFY_FAILED" in msg   # the SDK's hidden cause surfaces


def test_run_agent_llm_raises_when_unavailable(tmp_path, monkeypatch):
    monkeypatch.delitem(sys.modules, "anthropic", raising=False)
    coord = Coordinator("http://x", mode="llm")
    ctx, settings, _sb = _llm_ctx(coord, tmp_path)
    with pytest.raises(LLMUnavailable):
        llm_mod.run_agent_llm(ctx, system_prompt="s", task="t",
                              tool_names=["finish"], settings=settings)


# ---------------------------------------------------------------------------
# run_agent_llm — the tool-use loop
# ---------------------------------------------------------------------------
def test_loop_executes_tools_files_finding_and_finishes(tmp_path, monkeypatch):
    responses = [
        FakeResponse([
            FakeBlock("text", text="Let me probe the homepage first."),
            FakeBlock("tool_use", name="run_command",
                      input={"command": "curl -s -i http://x/"}, id="t1"),
        ]),
        FakeResponse([
            FakeBlock("tool_use", name="report_finding", id="t2", input={
                "title": "Leaked live key",
                "severity": "critical",
                "endpoint": "/static/app.js",
                "evidence": "sk_live_... embedded in client bundle",
                "remediation": "Rotate the key and move it server-side.",
                "cwe": "CWE-798",
            }),
        ]),
        FakeResponse([
            FakeBlock("tool_use", name="finish", input={"summary": "covered recon"}, id="t3"),
        ]),
    ]
    module = install_fake_anthropic(monkeypatch, responses)

    coord = Coordinator("http://x", mode="llm")
    ctx, settings, sandbox = _llm_ctx(coord, tmp_path, model="claude-opus-5")
    llm_mod.run_agent_llm(
        ctx,
        system_prompt="you are a pentester",
        task="Target: begin.",
        tool_names=["run_command", "report_finding", "finish"],
        settings=settings,
    )

    # terminated because the model called finish
    assert ctx.finished is True
    assert ctx.finish_summary == "covered recon"
    # report_finding really filed into the coordinator
    assert len(coord.findings) == 1
    assert coord.findings[0].title == "Leaked live key"
    assert coord.findings[0].severity == "critical"
    # exactly three model calls; each was billed (turns + cost)
    assert len(module.calls) == 3
    assert coord.turns >= 3
    assert coord.cost > 0
    # the assistant's text was surfaced as a 'think' event
    assert any(ev.level == "think" and "probe the homepage" in ev.message
               for ev in coord.events)
    # the run_command actually executed in the sandbox container
    assert sandbox.calls == ["curl -s -i http://x/"]
    # the model was handed the real tool schemas
    assert {t["name"] for t in module.calls[0]["tools"]} == \
        {"run_command", "report_finding", "finish"}


def test_loop_nudges_then_finishes_on_end_turn(tmp_path, monkeypatch):
    responses = [
        FakeResponse([FakeBlock("text", text="thinking out loud")], stop_reason="end_turn"),
        FakeResponse([FakeBlock("tool_use", name="finish", input={}, id="f1")]),
    ]
    module = install_fake_anthropic(monkeypatch, responses)

    coord = Coordinator("http://x", mode="llm")
    ctx, settings, _sb = _llm_ctx(coord, tmp_path)
    llm_mod.run_agent_llm(ctx, system_prompt="s", task="t",
                          tool_names=["run_command", "finish"], settings=settings)

    assert ctx.finished is True
    assert len(module.calls) == 2
    # the nudge appended a user turn before the second call
    assert module.calls[1]["messages"][-1]["role"] == "user"


def test_loop_stops_on_refusal(tmp_path, monkeypatch):
    responses = [FakeResponse([FakeBlock("text", text="no")], stop_reason="refusal")]
    module = install_fake_anthropic(monkeypatch, responses)

    coord = Coordinator("http://x", mode="llm")
    ctx, settings, _sb = _llm_ctx(coord, tmp_path)
    llm_mod.run_agent_llm(ctx, system_prompt="s", task="t",
                          tool_names=["finish"], settings=settings)

    assert ctx.finished is False
    assert len(module.calls) == 1
    assert coord.findings == []
    assert any(ev.level == "error" and "refusal" in ev.message for ev in coord.events)


def test_loop_stops_at_step_budget(tmp_path, monkeypatch):
    responses = [
        FakeResponse([FakeBlock("tool_use", name="run_command",
                                input={"command": "curl -s http://x/"}, id=f"s{i}")])
        for i in range(2)
    ]
    module = install_fake_anthropic(monkeypatch, responses)

    coord = Coordinator("http://x", mode="llm")
    ctx, settings, _sb = _llm_ctx(coord, tmp_path, max_steps=2)
    llm_mod.run_agent_llm(ctx, system_prompt="s", task="t",
                          tool_names=["run_command", "finish"], settings=settings)

    assert ctx.finished is False
    assert len(module.calls) == 2  # exactly the step budget
    assert any(ev.level == "think" and "budget" in ev.message for ev in coord.events)
