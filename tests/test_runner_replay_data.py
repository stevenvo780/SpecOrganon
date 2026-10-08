"""Replay data checks against real synthetic ledgers and local CLI processes."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import subprocess
import sys
from collections import OrderedDict
from enum import Enum
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from specorganon import engine, runner


AUTHOR = "agent:replay-test-author"


def nested(value, depth=40):
    for _ in range(depth):
        value = {"level": [value]}
    return value


@pytest.fixture
def case(tmp_path, monkeypatch):
    for key in os.environ:
        if key.startswith("ORGANON_"):
            monkeypatch.delenv(key)
    path = tmp_path / "case"
    engine.create_case(path, "Synthetic replay data test", "test data",
                       "human:replay-test-owner", approval_policy="local")
    return path


def manifest(data, expected_version=0):
    return {"schema": 1, "steps": [{
        "op": "put", "id": "p1", "kind": "problem", "text": "Synthetic checkpoint",
        "refs": [], "data": data, "expected_version": expected_version,
    }]}


def snapshot(case):
    return (case / "organon.json").read_bytes(), engine.get_state(case)


def checkpoint(case, data):
    result = runner.run_manifest(case, manifest(data), AUTHOR)
    assert result["applied"] == 1 and result["skipped"] == 0
    return snapshot(case)


@pytest.mark.parametrize(("stored", "replayed"), [
    (True, 1), (1, True), (False, 0), (0, False),
    (True, 1.0), (1.0, True), (False, 0.0), (0.0, False),
    (nested(True), nested(1)), (nested(0), nested(False)),
    (None, "null"), (None, False), ("1", 1), ("text", " text "),
    ("é", "e\u0301"), ([], {}), ([1, 2], [2, 1]), ([1], [1, 1]),
    ({"flag": False}, {"flag": 0}), ({"a": None}, {"b": None}),
    ({"items": [True, {"value": 0}]}, {"items": [1, {"value": False}]}),
])
def test_divergent_data_rejects_replay_without_changing_checkpoint(case, stored, replayed):
    before = checkpoint(case, {"value": stored})
    with pytest.raises(runner.ManifestError, match="step 0 diverges from item p1 version 1"):
        runner.run_manifest(case, manifest({"value": replayed}), AUTHOR)
    assert snapshot(case) == before


@pytest.mark.parametrize(("stored", "replayed"), [
    (None, None), (True, True), (False, False), ("text", "text"),
    ([], []), ({}, {}), (1, 1.0), (0, -0.0), (1.0, 1),
    (nested(1), nested(1.0)),
    ({"a": [None, True, 1, {"flag": False}], "b": "text"},
     {"b": "text", "a": [None, True, 1.0, {"flag": False}]}),
])
def test_equivalent_data_skips_replay_without_new_events(case, stored, replayed):
    before = checkpoint(case, {"value": stored})
    result = runner.run_manifest(case, manifest({"value": replayed}), AUTHOR)
    assert result["applied"] == 0 and result["skipped"] == 1
    assert snapshot(case) == before


def test_explicit_revision_is_idempotent_and_rejects_boolean_numeric_divergence(case):
    checkpoint(case, {"value": "initial"})
    revision = manifest({"nested": [False, None]}, expected_version=1)
    result = runner.run_manifest(case, revision, AUTHOR)
    assert result["applied"] == 1 and result["skipped"] == 0
    before = snapshot(case)
    assert before[1]["items"]["p1"]["version"] == 2
    result = runner.run_manifest(case, copy.deepcopy(revision), AUTHOR)
    assert result["applied"] == 0 and result["skipped"] == 1
    assert snapshot(case) == before
    revision["steps"][0]["data"] = {"nested": [0, None]}
    with pytest.raises(runner.ManifestError, match="step 0 diverges from item p1 version 2"):
        runner.run_manifest(case, revision, AUTHOR)
    assert snapshot(case) == before


def test_later_divergence_preserves_preceding_replay_checkpoint(case):
    plan = manifest({"value": True})
    second = copy.deepcopy(plan["steps"][0])
    second.update(id="p2", data={"value": False})
    plan["steps"].append(second)
    first = runner.run_manifest(case, plan, AUTHOR)
    assert first["applied"] == 2
    before = snapshot(case)
    second["data"] = {"value": 0}
    with pytest.raises(runner.ManifestError, match="step 1 diverges from item p2 version 1"):
        runner.run_manifest(case, plan, AUTHOR)
    assert snapshot(case) == before


@pytest.mark.parametrize(("stored", "replayed"), [(True, 1), (0, False)])
def test_cli_rejects_boolean_numeric_replay_without_changing_checkpoint(case, stored, replayed):
    before = checkpoint(case, {"nested": [stored]})
    plan = case.parent / "manifest.json"
    plan.write_text(json.dumps(manifest({"nested": [replayed]})), encoding="utf-8")
    source = Path(runner.__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-B", "-m", "specorganon.cli", "run", str(case),
         "--manifest", str(plan), "--actor", AUTHOR],
        cwd=case.parent, env={**os.environ, "PYTHONPATH": str(source)},
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout == ""
    assert result.stderr == "organon: step 0 diverges from item p1 version 1\n"
    assert snapshot(case) == before


@pytest.mark.parametrize(("stored", "replayed", "diverges"), [
    (True, 1, True), (0, False, True),
    ({"a": [None, 1, False], "b": "text"},
     {"b": "text", "a": [None, 1.0, False]}, False),
    (nested(True), nested(True), False),
])
def test_real_stdio_mcp_replay_preserves_checkpoint(case, stored, replayed, diverges):
    before = checkpoint(case, {"value": stored})
    source = Path(runner.__file__).resolve().parents[1]
    params = StdioServerParameters(
        command=sys.executable, args=["-B", "-m", "specorganon.server"],
        cwd=str(case.parent),
        env={**os.environ, "PYTHONPATH": str(source), "ORGANON_ROOT": str(case.parent)},
    )

    async def exercise():
        async with Client(params, mode="legacy") as client:
            result = await client.call_tool("run", {
                "path": str(case), "manifest": manifest({"value": replayed}),
                "actor": AUTHOR,
            })
            assert result.is_error is diverges, result.content
            if diverges:
                assert "step 0 diverges from item p1 version 1" in result.content[0].text
            else:
                response = result.structured_content or json.loads(result.content[0].text)
                assert response["applied"] == 0 and response["skipped"] == 1

    asyncio.run(asyncio.wait_for(exercise(), timeout=20))
    assert snapshot(case) == before


class ListValue(list):
    pass


class StringValue(str):
    pass


class StringChoice(str, Enum):
    TEXT = "text"


@pytest.mark.parametrize("data", [
    OrderedDict([("flag", True), ("value", 1)]),
    {"value": ListValue([True, None, 1])},
    {"value": StringValue("text")},
    {"value": StringChoice.TEXT},
], ids=["ordered-dict", "list-subclass", "str-subclass", "str-enum"])
def test_python_json_subclasses_replay_without_new_events(case, data):
    plan = manifest(data)
    first = runner.run_manifest(case, plan, AUTHOR)
    assert first["applied"] == 1 and first["skipped"] == 0
    before = snapshot(case)
    replay = runner.run_manifest(case, plan, AUTHOR)
    assert replay["applied"] == 0 and replay["skipped"] == 1
    assert snapshot(case) == before


@pytest.mark.parametrize(("stored", "replayed"), [
    (OrderedDict([("value", True)]), OrderedDict([("value", 1)])),
    ({"value": ListValue([False])}, {"value": ListValue([0])}),
    ({"value": StringValue("1")}, {"value": 1}),
    ({"value": StringChoice.TEXT}, {"value": True}),
], ids=["ordered-dict", "list-subclass", "str-subclass", "str-enum"])
def test_python_json_subclasses_keep_json_categories_distinct(case, stored, replayed):
    before = checkpoint(case, stored)
    with pytest.raises(runner.ManifestError, match="step 0 diverges from item p1 version 1"):
        runner.run_manifest(case, manifest(replayed), AUTHOR)
    assert snapshot(case) == before


@pytest.mark.parametrize("depth", [250, 300, 350, 400])
def test_deep_json_replay_preserves_checkpoint(case, depth):
    plan = manifest({"value": nested(True, depth)})
    first = runner.run_manifest(case, plan, AUTHOR)
    assert first["applied"] == 1 and first["skipped"] == 0
    before = (case / "organon.json").read_bytes()
    revision = engine.get_state(case)["revision"]
    replay = runner.run_manifest(case, plan, AUTHOR)
    assert replay["applied"] == 0 and replay["skipped"] == 1
    assert (case / "organon.json").read_bytes() == before
    state = engine.get_state(case)
    assert state["revision"] == revision and state["items"]["p1"]["version"] == 1


@pytest.mark.parametrize("depth", [250, 300, 350, 400])
def test_deep_json_boolean_numeric_divergence_preserves_checkpoint(case, depth):
    first = runner.run_manifest(case, manifest({"value": nested(True, depth)}), AUTHOR)
    assert first["applied"] == 1 and first["skipped"] == 0
    before = (case / "organon.json").read_bytes()
    revision = engine.get_state(case)["revision"]
    with pytest.raises(runner.ManifestError, match="step 0 diverges from item p1 version 1"):
        runner.run_manifest(case, manifest({"value": nested(1, depth)}), AUTHOR)
    assert (case / "organon.json").read_bytes() == before
    state = engine.get_state(case)
    assert state["revision"] == revision and state["items"]["p1"]["version"] == 1
