"""Raw stdio MCP frames must not lose JSON distinctions before tool dispatch."""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from pathlib import Path

import anyio
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp_types import INVALID_PARAMS, INVALID_REQUEST, PARSE_ERROR

from specorganon import ledger
from specorganon import server as mcp_server
from stdio_process import managed_stdio_process


MCP = Path(sys.executable).parent / "organon-mcp"


def _call(request_id: int, name: str, arguments: dict) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        separators=(",", ":"),
    )


async def _response(process: asyncio.subprocess.Process) -> dict:
    assert process.stdout is not None
    line = await asyncio.wait_for(process.stdout.readline(), timeout=5)
    assert line, "MCP process ended before its response"
    return json.loads(line)


def test_raw_stdio_rejects_ambiguous_frames_without_mutating_case(
    tmp_path: Path,
) -> None:
    case = tmp_path / "case"
    ledger.init_project(case, "Strict MCP", "test", "human", approval_policy="fixture")
    environment = {
        **os.environ,
        "ORGANON_ROOT": str(tmp_path),
        "ORGANON_ALLOW_FIXTURES": "1",
    }

    async def exercise() -> None:
        process = await asyncio.create_subprocess_exec(
            str(MCP),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        async with managed_stdio_process(process):
            assert process.stdin is not None
            initialize = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "raw-strict-test", "version": "1"},
                },
            }
            process.stdin.write((json.dumps(initialize) + "\n").encode())
            await process.stdin.drain()
            assert (await _response(process))["id"] == 1
            process.stdin.write(
                b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
            )
            await process.stdin.drain()

            first = {
                "path": "case",
                "id": "p1",
                "kind": "problem",
                "text": "Initial",
                "actor": "agent",
                "data": {},
            }
            process.stdin.write((_call(2, "put", first) + "\n").encode())
            await process.stdin.drain()
            accepted = await _response(process)
            assert accepted["id"] == 2 and accepted["result"]["isError"] is False
            before = ledger.project_file(case).read_bytes()

            base = {
                "path": "case",
                "id": "bad",
                "kind": "problem",
                "text": "Must not persist",
                "actor": "agent",
                "data": "MARKER",
            }
            template = _call(10, "put", base)
            invalid = [
                (
                    "nested duplicate",
                    template.replace('"MARKER"', '{"nested":{"value":1,"value":2}}'),
                    PARSE_ERROR,
                    "duplicate",
                ),
                (
                    "escaped duplicate",
                    template.replace('"MARKER"', '{"value":1,"\\u0076alue":2}'),
                    PARSE_ERROR,
                    "duplicate",
                ),
                (
                    "NaN",
                    template.replace('"MARKER"', '{"value":NaN}'),
                    PARSE_ERROR,
                    "non-finite",
                ),
                (
                    "Infinity",
                    template.replace('"MARKER"', '{"value":Infinity}'),
                    PARSE_ERROR,
                    "non-finite",
                ),
                (
                    "underflow",
                    template.replace('"MARKER"', '{"value":1e-9999}'),
                    PARSE_ERROR,
                    "underflows",
                ),
                (
                    "bool expected_version",
                    _call(
                        10,
                        "put",
                        {
                            **first,
                            "text": "Incorrect update",
                            "expected_version": True,
                        },
                    ),
                    INVALID_PARAMS,
                    "integer",
                ),
                (
                    "bool expected_deps",
                    _call(
                        10,
                        "put",
                        {
                            "path": "case",
                            "id": "a1",
                            "kind": "actor",
                            "text": "Incorrect actor",
                            "actor": "agent",
                            "refs": ["p1"],
                            "data": {},
                            "expected_version": 0,
                            "expected_deps": {"p1": True},
                        },
                    ),
                    INVALID_PARAMS,
                    "integer",
                ),
                (
                    "bool challenge_seq",
                    _call(
                        10,
                        "resolve_challenge",
                        {
                            "path": "case",
                            "challenge_seq": True,
                            "resolution_item": "p1",
                            "actor": "agent",
                        },
                    ),
                    INVALID_PARAMS,
                    "integer",
                ),
                (
                    "JSON string data",
                    _call(
                        10,
                        "put",
                        {
                            **base,
                            "data": '{"nested":{"value":1,"value":2}}',
                        },
                    ),
                    INVALID_PARAMS,
                    "put.data",
                ),
                (
                    "JSON string expected_deps",
                    _call(
                        10,
                        "put",
                        {
                            "path": "case",
                            "id": "a1",
                            "kind": "actor",
                            "text": "Bad deps",
                            "actor": "agent",
                            "refs": ["p1"],
                            "data": {},
                            "expected_version": 0,
                            "expected_deps": '{"p1":0,"p1":1}',
                        },
                    ),
                    INVALID_PARAMS,
                    "put.expected_deps",
                ),
                (
                    "JSON string refs",
                    _call(
                        10,
                        "put",
                        {
                            "path": "case",
                            "id": "a1",
                            "kind": "actor",
                            "text": "Bad refs",
                            "actor": "agent",
                            "refs": '["p1"]',
                            "data": {},
                        },
                    ),
                    INVALID_PARAMS,
                    "put.refs",
                ),
                (
                    "JSON string manifest",
                    _call(
                        10,
                        "run",
                        {
                            "path": "case",
                            "actor": "agent",
                            "manifest": (
                                '{"schema":1,"steps":[{"op":"put","id":"bad_run",'
                                '"kind":"actor","text":"Bad manifest","refs":["p1"],'
                                '"data":{"value":1,"value":2}}]}'
                            ),
                        },
                    ),
                    INVALID_PARAMS,
                    "run.manifest",
                ),
                (
                    "JSON string roles",
                    _call(
                        10,
                        "next_task",
                        {
                            "path": "case",
                            "roles": '{"writer":"a","writer":"b"}',
                        },
                    ),
                    INVALID_PARAMS,
                    "next_task.roles",
                ),
            ]
            for index, (label, raw, code, message) in enumerate(invalid, start=20):
                process.stdin.write((raw + "\n").encode())
                process.stdin.write(
                    (_call(index, "status", {"path": "case"}) + "\n").encode()
                )
                await process.stdin.drain()
                # The following status reply is a barrier proving the reject
                # reached the wire and the same server remains usable.
                errors = []
                while True:
                    reply = await _response(process)
                    if reply["id"] == index:
                        break
                    assert reply["id"] == 10 and "error" in reply, (label, reply)
                    errors.append(reply["error"])
                assert len(errors) == 1, label
                assert errors[0]["code"] == code, label
                assert message in errors[0]["message"].lower(), label
                assert ledger.project_file(case).read_bytes() == before, label

            ambiguous_id = _call(10, "put", first).replace(
                '"id":10,', '"id":10,"id":11,', 1
            )
            process.stdin.write((ambiguous_id + "\n").encode())
            process.stdin.write((_call(90, "status", {"path": "case"}) + "\n").encode())
            await process.stdin.drain()
            rejected_id = await _response(process)
            assert rejected_id["id"] is None
            assert rejected_id["error"]["code"] == PARSE_ERROR
            assert (await _response(process))["id"] == 90
            assert ledger.project_file(case).read_bytes() == before

            put_envelope = json.loads(_call(10, "put", {**base, "data": {}}))
            malformed_envelopes = [
                (
                    "request with result",
                    json.dumps({**put_envelope, "result": {}}),
                    10,
                    "response fields",
                ),
                (
                    "request with error",
                    json.dumps(
                        {
                            **put_envelope,
                            "error": {"code": -1, "message": "injected"},
                        }
                    ),
                    10,
                    "response fields",
                ),
                (
                    "request with unknown root field",
                    json.dumps({**put_envelope, "extra": "ignored by SDK"}),
                    10,
                    "envelope fields",
                ),
                ("batch", json.dumps([put_envelope]), None, "batch"),
                (
                    "boolean id",
                    json.dumps({**put_envelope, "id": True}),
                    None,
                    "id",
                ),
                (
                    "null id",
                    json.dumps({**put_envelope, "id": None}),
                    None,
                    "id",
                ),
                (
                    "array params",
                    json.dumps({**put_envelope, "params": []}),
                    10,
                    "params",
                ),
            ]
            for index, (label, raw, request_id, message) in enumerate(
                malformed_envelopes, start=110
            ):
                process.stdin.write((raw + "\n").encode())
                process.stdin.write(
                    (_call(index, "status", {"path": "case"}) + "\n").encode()
                )
                await process.stdin.drain()
                rejected = await _response(process)
                assert rejected["id"] == request_id, label
                assert rejected["error"]["code"] == INVALID_REQUEST, label
                assert message in rejected["error"]["message"].lower(), label
                assert (await _response(process))["id"] == index, label
                assert ledger.project_file(case).read_bytes() == before, label

            invalid_utf8 = template.encode().replace(
                b'"MARKER"', b'{"value":"invalid\xff"}'
            )
            process.stdin.write(invalid_utf8 + b"\n")
            process.stdin.write(
                (_call(130, "status", {"path": "case"}) + "\n").encode()
            )
            await process.stdin.drain()
            bad_encoding = await _response(process)
            assert bad_encoding["id"] is None
            assert bad_encoding["error"]["code"] == PARSE_ERROR
            assert "utf-8" in bad_encoding["error"]["message"].lower()
            assert (await _response(process))["id"] == 130
            assert ledger.project_file(case).read_bytes() == before

            process.stdin.write(
                (
                    _call(
                        100,
                        "put",
                        {
                            "path": "case",
                            "id": "valid",
                            "kind": "actor",
                            "text": "Valid after rejects",
                            "actor": "agent",
                            "data": {},
                            "refs": ["p1"],
                            "expected_version": 0,
                            "expected_deps": {"p1": 1},
                        },
                    )
                    + "\n"
                ).encode()
            )
            await process.stdin.drain()
            valid = await _response(process)
            assert valid["id"] == 100 and valid["result"]["isError"] is False
            assert [
                event["payload"]["id"] for event in ledger.read_project(case)["events"]
            ] == [
                "p1",
                "valid",
            ]

    asyncio.run(exercise())


def test_oversized_raw_line_is_drained_before_next_message(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "_MAX_MCP_LINE_BYTES", 128)
    valid = '{"jsonrpc":"2.0","id":1,"method":"ping"}\n'
    source = anyio.wrap_file(io.BytesIO(b"x" * 192 + b"\n" + valid.encode()))
    stdin = mcp_server._StrictStdin(source)

    class Writer:
        def __init__(self) -> None:
            self.messages = []

        async def send(self, message) -> None:
            self.messages.append(message.message)

    writer = Writer()
    stdin.attach_writer(writer)

    async def exercise() -> None:
        assert [line async for line in stdin] == [valid]

    asyncio.run(exercise())
    assert len(writer.messages) == 1
    assert writer.messages[0].id is None
    assert writer.messages[0].error.code == INVALID_REQUEST


def test_sdk_client_rejects_boolean_integer_arguments(tmp_path: Path) -> None:
    case = tmp_path / "case"
    ledger.init_project(
        case, "Strict integers", "test", "human", approval_policy="fixture"
    )
    environment = {
        **os.environ,
        "ORGANON_ROOT": str(tmp_path),
        "ORGANON_ALLOW_FIXTURES": "1",
    }

    async def exercise() -> None:
        params = StdioServerParameters(
            command=str(MCP), cwd=str(tmp_path), env=environment
        )
        async with Client(params, mode="legacy") as client:
            result = await client.call_tool(
                "put",
                {
                    "path": "case",
                    "id": "p1",
                    "kind": "problem",
                    "text": "Valid",
                    "actor": "agent",
                    "data": {},
                    "expected_version": 0,
                },
            )
            assert not result.is_error
            before = ledger.project_file(case).read_bytes()
            for name, arguments in (
                (
                    "put",
                    {
                        "path": "case",
                        "id": "p1",
                        "kind": "problem",
                        "text": "Boolean version",
                        "actor": "agent",
                        "data": {},
                        "expected_version": True,
                    },
                ),
                (
                    "put",
                    {
                        "path": "case",
                        "id": "a1",
                        "kind": "actor",
                        "text": "Boolean dependency",
                        "actor": "agent",
                        "refs": ["p1"],
                        "data": {},
                        "expected_version": 0,
                        "expected_deps": {"p1": True},
                    },
                ),
                (
                    "resolve_challenge",
                    {
                        "path": "case",
                        "challenge_seq": True,
                        "resolution_item": "p1",
                        "actor": "agent",
                    },
                ),
            ):
                try:
                    rejected = await client.call_tool(name, arguments)
                except Exception as exc:
                    assert (
                        "integer" in str(exc).lower() or "int_type" in str(exc).lower()
                    )
                else:
                    assert rejected.is_error
                assert ledger.project_file(case).read_bytes() == before

    asyncio.run(exercise())
