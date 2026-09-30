"""Retirement transports and bounded runner behavior on synthetic controls.

The controls exercise declared lineage mechanics, never empirical evidence or
human authority. Runner phase focusing changes a copied response only; it does
not approve or advance any case phase.
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path

import pytest

from specorganon import cli, engine, runner
from specorganon.ledger import read_project
from specorganon.workflow import PHASES


ROOT = Path(__file__).resolve().parents[1]


def _arguments(case: Path) -> dict:
    return {
        "path": str(case), "id": "old", "replacements": {"new": 1},
        "reason": "Synthetic technical replacement", "actor": "agent:executor",
        "expected_version": 1, "expected_review_seq": 12,
    }


def _argv(arguments: dict) -> list[str]:
    return [
        "retire-indicator", arguments["path"], arguments["id"],
        "--replacements", json.dumps(arguments["replacements"]),
        "--expected-version", str(arguments["expected_version"]),
        "--expected-review-seq", str(arguments["expected_review_seq"]),
        "--reason", arguments["reason"], "--actor", arguments["actor"],
    ]


def _server():
    pytest.importorskip("mcp", reason="MCP dependency unavailable in this interpreter")
    from specorganon import server

    return server


def _case(tmp_path: Path, monkeypatch, name: str = "case") -> tuple[Path, dict]:
    registry = tmp_path / "public-registry.json"
    if not registry.exists():
        registry.write_text(json.dumps({"schema": 2, "cases": {}}), encoding="utf-8")
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    monkeypatch.delenv("ORGANON_LEDGER_ANCHORS_FILE", raising=False)
    case = tmp_path / name
    engine.create_case(case, "Synthetic retirement interfaces", "test", "agent:author")
    nodes = [
        ("p1", "problem", [], {}),
        ("a1", "actor", ["p1"], {}),
        ("b1", "boundary", ["p1"], {}),
        ("n1", "norm", ["p1", "a1"], {}),
        ("q1", "question", ["p1"], {}),
        ("h1", "hypothesis", ["q1"], {}),
        ("pr", "protocol", ["h1", "q1"], {
            "population": "synthetic control only", "method": "declared mechanics fixture",
            "comparison": "same synthetic metric", "uncertainty": "no empirical measurements",
        }),
        ("e1", "evidence", ["pr"], {
            "origin": "derived", "source": "synthetic-control", "date": "2026-09-30",
            "locator": "value", "metric_key": "synthetic_fraction", "scope": "synthetic",
            "unit": "fraction", "value": "0.5",
        }),
        ("old", "indicator", ["p1", "n1", "pr", "e1"], {
            "metric": "synthetic_fraction", "unit": "fraction", "value": "0.5",
        }),
        ("new", "indicator", ["p1", "n1", "pr", "e1"], {
            "metric": "synthetic_fraction", "unit": "fraction", "value": "0.5",
        }),
    ]
    for id, kind, refs, data in nodes:
        engine.put_item(case, id, kind, f"Synthetic {kind}: {id}", refs, data, "agent:author")
    review = engine.review_item(case, "old", "reject", "Synthetic technical rejection", "agent:reviewer")
    arguments = _arguments(case)
    arguments["expected_review_seq"] = review["seq"]
    return case, arguments


def test_cli_parser_dispatches_exact_mandatory_guards(tmp_path, monkeypatch, capsys):
    arguments = _arguments(tmp_path / "unused")
    calls = []

    def invoke(operation, **kwargs):
        calls.append((operation, kwargs))
        return {"kind": "indicator_retire", "payload": kwargs}

    monkeypatch.setattr(cli, "invoke", invoke)
    assert cli.main(_argv(arguments)) == 0
    assert calls == [("retire_indicator", arguments)]
    assert json.loads(capsys.readouterr().out)["kind"] == "indicator_retire"


@pytest.mark.parametrize("flag", [
    "--replacements", "--expected-version", "--expected-review-seq", "--reason", "--actor",
])
def test_cli_requires_every_retirement_guard(tmp_path, flag):
    argv = _argv(_arguments(tmp_path / "unused"))
    index = argv.index(flag)
    del argv[index:index + 2]
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(argv)
    assert exc.value.code == 2


@pytest.mark.parametrize("raw", [
    '[]', 'null', '{"new":true}', '{"new":1.0}', '{"new":"1"}',
    '{"new":1,"new":2}', '{"new":1,"\\u006eew":2}',
    '{"new":NaN}', '{"new":Infinity}', '{"new":{"version":1}}',
])
def test_cli_rejects_ambiguous_replacements_before_dispatch(tmp_path, monkeypatch, raw):
    argv = _argv(_arguments(tmp_path / "unused"))
    argv[argv.index("--replacements") + 1] = raw

    def forbidden(*args, **kwargs):
        pytest.fail("invalid retirement reached dispatch")

    monkeypatch.setattr(cli, "invoke", forbidden)
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2
    assert not (tmp_path / "unused").exists()


def test_shared_invoke_calls_retirement_engine(tmp_path, monkeypatch):
    arguments = _arguments(tmp_path / "unused")
    calls = []

    def retire_indicator(**kwargs):
        calls.append(kwargs)
        return {"kind": "indicator_retire"}

    monkeypatch.setattr(engine, "retire_indicator", retire_indicator)
    assert cli.invoke("retire_indicator", **arguments) == {"kind": "indicator_retire"}
    assert calls == [arguments]


def test_cli_retirement_records_one_event_and_no_approval(tmp_path, monkeypatch, capsys):
    case, arguments = _case(tmp_path, monkeypatch)
    before = read_project(case)["events"]
    assert cli.main(_argv(arguments)) == 0
    event = json.loads(capsys.readouterr().out)
    after = read_project(case)["events"]
    assert after[:-1] == before
    assert event == after[-1]
    assert event["kind"] == "indicator_retire"
    assert event["payload"]["replacements"] == {"new": 1}
    assert engine.get_state(case)["items"]["old"]["retired"] is True
    assert not any(e["kind"] in {"approval", "phase_review", "phase_advance"} for e in after)
    frozen = (case / "organon.json").read_bytes()
    arguments["expected_review_seq"] += 1
    assert cli.main(_argv(arguments)) == 1
    assert (case / "organon.json").read_bytes() == frozen


@pytest.mark.parametrize("field,value", [
    ("expected_version", 0), ("expected_review_seq", 0), ("replacements", {}),
    ("replacements", {"new": 0}), ("replacements", {"new": -1}),
])
def test_cli_leaves_semantic_positive_validation_to_engine(
    tmp_path, monkeypatch, capsys, field, value,
):
    case, arguments = _case(tmp_path, monkeypatch)
    arguments[field] = value
    before = (case / "organon.json").read_bytes()
    assert cli.main(_argv(arguments)) == 1
    assert (case / "organon.json").read_bytes() == before
    assert capsys.readouterr().err


@pytest.mark.parametrize("field,value", [
    ("replacements", []), ("replacements", None), ("replacements", {"new": True}),
    ("replacements", {"new": 1.0}), ("replacements", {"new": "1"}),
    ("expected_version", True), ("expected_version", 1.0), ("expected_version", "1"),
    ("expected_review_seq", True), ("expected_review_seq", 1.0), ("expected_review_seq", "1"),
])
def test_mcp_raw_layer_rejects_type_coercion(tmp_path, field, value):
    server = _server()
    arguments = _arguments(tmp_path / "unused")
    arguments[field] = value
    message = {"method": "tools/call", "params": {"name": "retire_indicator", "arguments": arguments}}
    with pytest.raises(ValueError, match="retire_indicator"):
        server._validate_raw_tool_arguments(message)


def test_mcp_direct_transport_records_actual_retirement(tmp_path, monkeypatch):
    server = _server()
    case, arguments = _case(tmp_path, monkeypatch)
    monkeypatch.setenv("ORGANON_ROOT", str(tmp_path))
    before = read_project(case)["events"]
    event = server.retire_indicator(**arguments)
    after = read_project(case)["events"]
    assert after[:-1] == before and event == after[-1]
    assert event["kind"] == "indicator_retire"
    state = engine.get_state(case)
    assert state["items"]["old"]["retired"] is True
    assert state["items"]["n1"]["approved"] is False


def test_real_mcp_discovery_raw_failures_and_success(tmp_path, monkeypatch):
    _server()
    case, arguments = _case(tmp_path, monkeypatch)
    original = (case / "organon.json").read_bytes()

    async def exercise():
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "specorganon.server",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin", "LANG": "C.UTF-8",
                 "PYTHONPATH": str(ROOT / "src"), "ORGANON_ROOT": str(tmp_path),
                 "ORGANON_APPROVERS_FILE": str(tmp_path / "public-registry.json")},
        )
        assert process.stdin is not None and process.stdout is not None

        async def exchange(message):
            raw = message if isinstance(message, str) else json.dumps(message)
            process.stdin.write((raw + "\n").encode())
            await process.stdin.drain()
            line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
            assert line, "MCP process ended before response"
            return json.loads(line)

        def request(id, args):
            return {"jsonrpc": "2.0", "id": id, "method": "tools/call",
                    "params": {"name": "retire_indicator", "arguments": args}}

        try:
            initialized = await exchange({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                          "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                     "clientInfo": {"name": "retirement-test", "version": "1"}}})
            assert "result" in initialized
            process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            await process.stdin.drain()
            listed = await exchange({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            tool = next(x for x in listed["result"]["tools"] if x["name"] == "retire_indicator")
            schema = tool["inputSchema"]
            assert set(arguments) <= set(schema["required"])
            assert schema["properties"]["replacements"]["additionalProperties"]["type"] == "integer"
            bad = copy.deepcopy(arguments)
            bad["replacements"] = "MARKER"
            duplicate = json.dumps(request(3, bad)).replace('"MARKER"', '{"new":1,"new":2}')
            response = await exchange(duplicate)
            assert response["error"]["code"] == -32700
            assert (case / "organon.json").read_bytes() == original
            for index, (field, value) in enumerate([
                ("replacements", {"new": True}), ("replacements", {"new": "1"}),
                ("expected_version", True), ("expected_review_seq", "1"),
            ], 4):
                bad = copy.deepcopy(arguments)
                bad[field] = value
                response = await exchange(request(index, bad))
                assert response["error"]["code"] == -32602
                assert (case / "organon.json").read_bytes() == original
            response = await exchange(request(8, arguments))
            result = response["result"]
            assert not result.get("isError", False), result
            event = result.get("structuredContent") or json.loads(result["content"][0]["text"])
            assert event == read_project(case)["events"][-1]
            assert event["kind"] == "indicator_retire"
            assert engine.get_state(case)["items"]["old"]["retired"] is True
        finally:
            process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                process.terminate()
                await process.wait()

    asyncio.run(exercise())


def _focus(state: dict, phase: str) -> dict:
    state = copy.deepcopy(state)
    for candidate in PHASES:
        if candidate.id == phase:
            break
        state["phases"][candidate.id]["accepted"] = True
    state["phases"][phase].update(ready=True, reviewed=False, blockers=[])
    return state


def test_runner_ignores_only_effective_retired_troubled_indicator(tmp_path, monkeypatch):
    case, arguments = _case(tmp_path, monkeypatch)
    engine.retire_indicator(**arguments)
    state = _focus(engine.get_state(case), "study")
    assert state["items"]["old"]["issues"]
    monkeypatch.setattr(engine, "get_state", lambda path: copy.deepcopy(state))
    task = runner.next_task(case)
    assert task["action"] == "review_phase"
    assert "old" not in {x["id"] for x in task["artifacts"]["items"]}
    assert "new" in {x["id"] for x in task["artifacts"]["items"]}
    assert not any(x["kind"] == "indicator" for x in task["missing"])
    state["items"]["old"]["retired"] = False
    state["items"]["old"]["retirement_status"] = "invalidated"
    task = runner.next_task(case)
    assert task["action"] == "repair_artifacts"
    assert "old" in {x["id"] for x in task["artifacts"]["items"]}


def test_runner_minima_count_only_active_indicators(tmp_path, monkeypatch):
    case, arguments = _case(tmp_path, monkeypatch)
    engine.retire_indicator(**arguments)
    state = _focus(engine.get_state(case), "study")
    # Defensive runner boundary: an empty active set must still fail its minimum,
    # even if a future producer incorrectly retained an effective retirement flag.
    del state["items"]["new"]
    state["phases"]["study"]["ready"] = False
    monkeypatch.setattr(engine, "get_state", lambda path: copy.deepcopy(state))
    task = runner.next_task(case)
    assert task["action"] == "create_artifacts"
    assert next(x for x in task["missing"] if x["kind"] == "indicator") == {
        "kind": "indicator", "required": 1, "valid": 0, "remaining": 1,
    }


def test_runner_prior_context_excludes_retired_indicators(tmp_path, monkeypatch):
    case, arguments = _case(tmp_path, monkeypatch)
    engine.retire_indicator(**arguments)
    state = _focus(engine.get_state(case), "observe")
    monkeypatch.setattr(engine, "get_state", lambda path: copy.deepcopy(state))
    task = runner.next_task(case)
    ids = {x["id"] for x in task["inputs"]["items"]}
    assert "new" in ids and "old" not in ids


def test_manifest_cannot_hide_retirement_in_a_batch(tmp_path, monkeypatch):
    case, arguments = _case(tmp_path, monkeypatch)
    before = (case / "organon.json").read_bytes()
    manifest = {"schema": 1, "steps": [{"op": "retire_indicator", **arguments}]}
    with pytest.raises(runner.ManifestError, match="unsupported op"):
        runner.run_manifest(case, manifest, "agent:executor")
    assert (case / "organon.json").read_bytes() == before
