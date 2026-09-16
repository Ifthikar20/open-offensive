"""The shared tool layer: the registry, schemas, the in-container run_command
tool, findings, and the never-raises dispatcher.

Every tool runs INSIDE the sandbox now, so a :class:`FakeSandbox`-backed
``ToolContext`` stands in for the container: ``run_command`` executes against it
and the command is recorded, ``report_finding`` files into the coordinator, and
``execute`` turns every error into text rather than raising.
"""

from __future__ import annotations

from conftest import make_agent, tool_ctx

from openoffensive import Coordinator
from openoffensive.sandbox.fake import FakeSandbox
from openoffensive.tools import REGISTRY, ToolContext, anthropic_schemas, execute

_EXPECTED_TOOLS = {"run_command", "read_file", "report_finding",
                   "load_skill", "list_skills", "finish"}


# ---------------------------------------------------------------------------
# registry & schemas
# ---------------------------------------------------------------------------
def test_registry_has_expected_tools():
    assert set(REGISTRY) == _EXPECTED_TOOLS
    # the removed host-side HTTP tool must be gone
    assert "http_request" not in REGISTRY


def test_every_tool_schema_is_a_json_object():
    for name, tool in REGISTRY.items():
        schema = tool.input_schema
        assert isinstance(schema, dict), name
        assert schema.get("type") == "object", name
        assert "properties" in schema, name


def test_anthropic_schema_shape():
    schemas = anthropic_schemas(sorted(_EXPECTED_TOOLS))
    assert len(schemas) == len(_EXPECTED_TOOLS)
    for s in schemas:
        assert set(s) == {"name", "description", "input_schema"}
        assert s["input_schema"]["type"] == "object"
    # A single tool exposes the same three keys.
    solo = REGISTRY["run_command"].anthropic_schema()
    assert solo["name"] == "run_command"
    assert solo["input_schema"]["required"] == ["command"]


def test_anthropic_schemas_ignores_unknown_names():
    assert anthropic_schemas(["run_command", "does_not_exist"]) == \
        [REGISTRY["run_command"].anthropic_schema()]


# ---------------------------------------------------------------------------
# run_command — executes in the sandbox and records the container command
# ---------------------------------------------------------------------------
def test_run_command_executes_in_sandbox_and_records_it():
    coord = Coordinator("http://t")
    sandbox = FakeSandbox(default=("SERVER BANNER", 0))
    ctx = tool_ctx(coord, sandbox=sandbox, target="http://t")

    out = execute(ctx, "run_command", {"command": "curl -s -i http://t/"})
    assert "SERVER BANNER" in out
    # the command really ran in the container (recorded by the sandbox)
    assert sandbox.calls == ["curl -s -i http://t/"]
    # and a tool event was logged
    assert any(ev.level == "tool" and "curl -s -i http://t/" in ev.message
               for ev in coord.events)


def test_run_command_empty_is_rejected():
    coord = Coordinator("http://t")
    ctx = tool_ctx(coord, sandbox=FakeSandbox())
    out = execute(ctx, "run_command", {"command": "   "})
    assert out.startswith("error:")
    assert "non-empty" in out


def test_read_file_wraps_cat_in_the_sandbox():
    coord = Coordinator("http://t")
    sandbox = FakeSandbox(responses={"cat /workspace/app.js": ("secret=sk_live_x", 0)})
    ctx = tool_ctx(coord, sandbox=sandbox)
    out = execute(ctx, "read_file", {"path": "/workspace/app.js"})
    assert "sk_live_x" in out
    assert any(c.startswith("cat ") for c in sandbox.calls)


# ---------------------------------------------------------------------------
# report_finding files into the coordinator
# ---------------------------------------------------------------------------
def test_report_finding_files_into_coordinator():
    coord = Coordinator("http://t")
    ctx = tool_ctx(coord, sandbox=FakeSandbox())
    assert coord.findings == []

    out = execute(ctx, "report_finding", {
        "title": "Test finding",
        "severity": "high",
        "endpoint": "/x",
        "evidence": "because",
        "remediation": "fix it",
        "cwe": "CWE-1",
    })
    assert "Filed" in out
    assert len(coord.findings) == 1
    f = coord.findings[0]
    assert f.title == "Test finding"
    assert f.severity == "high"
    assert f.id  # coordinator assigned an id
    assert f.cvss == 7.8


def test_report_finding_normalises_bad_severity():
    coord = Coordinator("http://t")
    ctx = tool_ctx(coord, sandbox=FakeSandbox())
    ctx.report(title="t", severity="SUPER-BAD", endpoint="/x",
               evidence="e", remediation="r")
    assert coord.findings[0].severity == "info"


def test_report_finding_auto_attaches_last_command_as_provenance():
    # An LLM-filed finding (no command/output passed to report_finding) is still
    # stamped with the agent's most recent container command + its real output,
    # so the finding is traceable to actual sandbox I/O rather than asserted.
    coord = Coordinator("http://t")
    sandbox = FakeSandbox(default=("Server: JuiceBox/0.1\nX: y", 0))
    ctx = tool_ctx(coord, sandbox=sandbox, target="http://t")

    execute(ctx, "run_command", {"command": "curl -s -i http://t/"})
    execute(ctx, "report_finding", {
        "title": "Server disclosure", "severity": "info", "endpoint": "/",
        "evidence": "banner shown", "remediation": "hide it",
    })
    f = coord.findings[0]
    assert f.command == "curl -s -i http://t/"          # the real last command
    assert "Server: JuiceBox/0.1" in f.output           # the real output it returned


def test_report_finding_keeps_explicit_provenance():
    # When a scripted playbook passes command/output explicitly, they win over the
    # last-command fallback (a finding can quote a command run earlier).
    coord = Coordinator("http://t")
    sandbox = FakeSandbox(default=("later output", 0))
    ctx = tool_ctx(coord, sandbox=sandbox, target="http://t")
    ctx.run("curl A")                                   # sets last_command = "curl A"
    ctx.report(title="t", severity="low", endpoint="/x", evidence="e", remediation="r",
               command="curl EARLIER", output="the matched line")
    f = coord.findings[0]
    assert f.command == "curl EARLIER"
    assert f.output == "the matched line"


# ---------------------------------------------------------------------------
# skills tools
# ---------------------------------------------------------------------------
def test_list_skills_returns_catalog():
    coord = Coordinator("http://t")
    ctx = tool_ctx(coord, sandbox=FakeSandbox())
    out = execute(ctx, "list_skills", {})
    assert "reconnaissance" in out
    assert "sql_injection" in out


def test_load_skill_known_and_unknown():
    coord = Coordinator("http://t")
    ctx = tool_ctx(coord, sandbox=FakeSandbox())
    known = execute(ctx, "load_skill", {"name": "sql_injection"})
    assert "skill: sql_injection" in known
    unknown = execute(ctx, "load_skill", {"name": "no_such_skill"})
    assert "No skill named" in unknown


# ---------------------------------------------------------------------------
# execute() dispatch — errors come back as text, never raise
# ---------------------------------------------------------------------------
def test_execute_unknown_tool_returns_error_string():
    coord = Coordinator("http://t")
    ctx = tool_ctx(coord, sandbox=FakeSandbox())
    out = execute(ctx, "no_such_tool", {})
    assert out.startswith("error:")
    assert "unknown tool" in out


def test_execute_bad_args_returns_error_string():
    coord = Coordinator("http://t")
    ctx = tool_ctx(coord, sandbox=FakeSandbox())

    # missing required 'command'
    missing = execute(ctx, "run_command", {})
    assert missing.startswith("error:")
    assert "bad arguments" in missing

    # unexpected keyword argument
    unexpected = execute(ctx, "run_command", {"command": "x", "bogus": 1})
    assert unexpected.startswith("error:")
    assert "bad arguments" in unexpected


def test_execute_never_raises_on_none_args():
    coord = Coordinator("http://t")
    ctx = tool_ctx(coord, sandbox=FakeSandbox())
    # list_skills takes no args; None args must be tolerated, not raise.
    out = execute(ctx, "list_skills", None)
    assert isinstance(out, str)
    assert "reconnaissance" in out


def test_finish_tool_sets_finished_flag():
    coord = Coordinator("http://t")
    ctx = tool_ctx(coord, sandbox=FakeSandbox())
    assert ctx.finished is False
    out = execute(ctx, "finish", {"summary": "all done"})
    assert ctx.finished is True
    assert ctx.finish_summary == "all done"
    assert "complete" in out


# ---------------------------------------------------------------------------
# ToolContext construction (the new 5-arg signature)
# ---------------------------------------------------------------------------
def test_tool_context_carries_sandbox_and_target():
    coord = Coordinator("http://t")
    sandbox = FakeSandbox()
    from openoffensive import Settings
    ctx = ToolContext(coord, make_agent(), Settings(), sandbox, "http://t")
    assert ctx.sandbox is sandbox
    assert ctx.target == "http://t"
    assert ctx.finished is False
