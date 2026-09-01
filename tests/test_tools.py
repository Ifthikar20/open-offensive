"""The shared tool layer: the registry, schemas, the scope-guarded HTTP tool,
findings, and the never-raises dispatcher."""

from __future__ import annotations

import dataclasses

from conftest import build_settings, make_agent

from openoffensive import Coordinator
from openoffensive.tools import (
    REGISTRY,
    Response,
    ToolContext,
    anthropic_schemas,
    execute,
)

_EXPECTED_TOOLS = {"http_request", "report_finding", "load_skill", "list_skills", "finish"}


# ---------------------------------------------------------------------------
# registry & schemas
# ---------------------------------------------------------------------------
def test_registry_has_expected_tools():
    assert set(REGISTRY) == _EXPECTED_TOOLS


def test_every_tool_schema_is_a_json_object(tmp_path):
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
    solo = REGISTRY["http_request"].anthropic_schema()
    assert solo["name"] == "http_request"
    assert solo["input_schema"]["required"] == ["path"]


def test_anthropic_schemas_ignores_unknown_names():
    assert anthropic_schemas(["http_request", "does_not_exist"]) == \
        [REGISTRY["http_request"].anthropic_schema()]


# ---------------------------------------------------------------------------
# ToolContext.http — reaches the target, and enforces the scope allowlist
# ---------------------------------------------------------------------------
def test_http_reaches_target_and_returns_response(demo_target, fast_settings):
    coord = Coordinator(demo_target)
    ctx = ToolContext(coord, make_agent(), fast_settings)

    before = coord.turns
    resp = ctx.http("/")
    assert isinstance(resp, Response)
    assert resp.status == 200
    assert "Juice-Box" in resp.body
    # a real, in-scope request is billed
    assert coord.turns == before + 1


def test_allowed_hosts_include_target_and_scope(demo_target, tmp_path):
    settings = build_settings(tmp_path, scope_allow=("extra.example",))
    coord = Coordinator(demo_target)
    ctx = ToolContext(coord, make_agent(), settings)
    assert "127.0.0.1" in ctx.allowed_hosts
    assert "extra.example" in ctx.allowed_hosts


def test_http_blocks_out_of_scope_host(demo_target, fast_settings):
    coord = Coordinator(demo_target)
    ctx = ToolContext(coord, make_agent(), fast_settings)
    # The context was scoped to the demo host only; redirect it at an unrelated
    # host to exercise the allowlist. The guard runs before any network call.
    ctx.target = "http://attacker.invalid"
    billed_before = coord.turns

    resp = ctx.http("/")
    assert resp.status == 0
    assert "out of scope" in resp.body or "blocked" in resp.body
    # blocked probes are neither billed nor sent
    assert coord.turns == billed_before
    # and a BLOCKED tool event was logged
    assert any(not ev.data.get("ok", True) and "BLOCKED" in ev.message
               for ev in coord.events)


def test_http_tool_handler_blocks_out_of_scope(demo_target, fast_settings):
    # Same guard, reached through the registered handler / execute() path.
    coord = Coordinator(demo_target)
    ctx = ToolContext(coord, make_agent(), fast_settings)
    ctx.target = "http://somewhere-else.invalid"
    out = execute(ctx, "http_request", {"path": "/admin"})
    assert "HTTP 0" in out
    assert "out of scope" in out or "blocked" in out


# ---------------------------------------------------------------------------
# report_finding files into the coordinator
# ---------------------------------------------------------------------------
def test_report_finding_files_into_coordinator(demo_target, fast_settings):
    coord = Coordinator(demo_target)
    ctx = ToolContext(coord, make_agent(), fast_settings)
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


def test_report_finding_normalises_bad_severity(demo_target, fast_settings):
    coord = Coordinator(demo_target)
    ctx = ToolContext(coord, make_agent(), fast_settings)
    ctx.report(title="t", severity="SUPER-BAD", endpoint="/x",
               evidence="e", remediation="r")
    assert coord.findings[0].severity == "info"


# ---------------------------------------------------------------------------
# execute() dispatch — errors come back as text, never raise
# ---------------------------------------------------------------------------
def test_execute_unknown_tool_returns_error_string(demo_target, fast_settings):
    coord = Coordinator(demo_target)
    ctx = ToolContext(coord, make_agent(), fast_settings)
    out = execute(ctx, "no_such_tool", {})
    assert out.startswith("error:")
    assert "unknown tool" in out


def test_execute_bad_args_returns_error_string(demo_target, fast_settings):
    coord = Coordinator(demo_target)
    ctx = ToolContext(coord, make_agent(), fast_settings)

    # missing required 'path'
    missing = execute(ctx, "http_request", {})
    assert missing.startswith("error:")
    assert "bad arguments" in missing

    # unexpected keyword argument
    unexpected = execute(ctx, "http_request", {"path": "/", "bogus": 1})
    assert unexpected.startswith("error:")
    assert "bad arguments" in unexpected


def test_execute_never_raises_on_none_args(demo_target, fast_settings):
    coord = Coordinator(demo_target)
    ctx = ToolContext(coord, make_agent(), fast_settings)
    # list_skills takes no args; None args must be tolerated, not raise.
    out = execute(ctx, "list_skills", None)
    assert isinstance(out, str)
    assert "reconnaissance" in out


def test_finish_tool_sets_finished_flag(demo_target, fast_settings):
    coord = Coordinator(demo_target)
    ctx = ToolContext(coord, make_agent(), fast_settings)
    assert ctx.finished is False
    out = execute(ctx, "finish", {"summary": "all done"})
    assert ctx.finished is True
    assert ctx.finish_summary == "all done"
    assert "complete" in out
