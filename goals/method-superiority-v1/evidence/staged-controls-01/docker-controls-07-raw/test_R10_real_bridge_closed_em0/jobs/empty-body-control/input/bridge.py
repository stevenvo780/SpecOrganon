"""Text-only native provider adapter, invoked inside an isolated role container.

Profiles are supplied by the operator as their original mounts. This script never
copies credentials, chooses another account, writes a ledger or approves a phase.
Raw provider streams remain under /output; the host journal measures this process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tomllib

from specorganon.role_jobs import JobStore, JobError, _read, _write, canonical, digest
from specorganon.ledger import strict_json_loads


from specorganon.native_transcript import (NativeRoleError,strict,response_json,parse_native,
    parse_gemini_stream,validate_codex_features,validate_result)


# Observed in the installed Codex 0.160.0 feature catalogue. Disable command,
# browser, media and delegation routes before execution, in addition to MCP.
# This does not authenticate identities or protect against a malicious client.
from specorganon.native_response_contract import CODEX_TEXT_ONLY_DISABLED


def read_request(path):
    try: return _read(path, 128_000)
    except JobError as exc: raise NativeRoleError("request must be bounded regular data") from exc


def render_prompt(raw):
    from specorganon.native_response_contract import render_prompt as shared
    try: return shared(raw)
    except ValueError as exc: raise NativeRoleError(str(exc)) from exc


def author_format_from_request(request):
    from specorganon.native_response_contract import author_format_from_request as shared
    try: return shared(request)
    except ValueError as exc: raise NativeRoleError(str(exc)) from exc


def response_contract_from_request(request):
    from specorganon.native_response_contract import response_contract_from_request as shared
    try: return shared(request)
    except ValueError as exc: raise NativeRoleError(str(exc)) from exc


def execution_identity(provider, executable):
    """Bind runtime identity without reading credentials or claiming isolation.

    The launcher must supply the inspected immutable Docker image ID. Original
    profiles remain a trusted operator boundary; the client may refresh its
    own session. This hashes only the known configuration file, never auth.
    """
    image = os.environ.get("SPECORGANON_ROLE_IMAGE_ID", "")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None:
        raise NativeRoleError("launcher must bind the inspected execution image")
    path = Path(executable).resolve(strict=True)
    with path.open("rb") as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > 536_870_912:
            raise NativeRoleError("unsupported native executable")
        hash_value = hashlib.sha256()
        while block := file.read(1_048_576): hash_value.update(block)
        after = os.fstat(file.fileno())
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise NativeRoleError("native executable changed during measurement")
    if provider == "codex":
        config = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    else:
        config = Path.home() / ".gemini/settings.json"
    return {"schema": 1, "image_id": image, "executable_path": str(path),
            "executable_sha256": hash_value.hexdigest(), "known_configuration_path": str(config),
            "known_configuration_sha256": digest(_read(config, 128_000)) if config.exists() else None,
            "other_effective_configuration": "unknown; trusted launcher/profile boundary"}


def native_argv(provider, model, prompt, *, model_catalog=None, reasoning_effort=None):
    from specorganon.native_response_contract import native_command
    names=[]
    if provider=='codex':
        home=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
        config=home/'config.toml'
        if config.exists():
            servers=tomllib.loads(_read(config,128000).decode()).get('mcp_servers',{})
            if type(servers) is not dict:raise NativeRoleError('invalid MCP configuration')
            names=list(servers)
    try:return native_command(provider,model,model_catalog=model_catalog,reasoning_effort=reasoning_effort,mcp_names=names)
    except ValueError as exc:raise NativeRoleError(str(exc)) from exc


def role_model_catalog(value,model):
    from specorganon.native_response_contract import role_model_catalog as shared
    try:return shared(value,model)
    except ValueError as exc:raise NativeRoleError(str(exc)) from exc

def codex_feature_argv(native_args):
    args = [native_args[0]]
    for index, value in enumerate(native_args[:-1]):
        if value in {"--disable", "-c"}: args += [value, native_args[index + 1]]
    return args + ["features", "list"]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["gemini", "codex"], required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-catalog", type=Path)
    parser.add_argument("--expected-executable-sha256")
    parser.add_argument("--codex-reasoning-effort", choices=("low", "medium", "high", "xhigh"))
    options = parser.parse_args(argv)
    options.output_dir.mkdir(parents=True, exist_ok=True)
    raw = read_request(options.request)
    request, prompt = render_prompt(raw)
    requested_author_format = author_format_from_request(request)
    executable = "/usr/local/bin/codex" if options.provider == "codex" else "/usr/local/bin/agy"
    identity_before = execution_identity(options.provider, executable)
    if options.provider=='gemini' and (type(options.expected_executable_sha256) is not str
            or re.fullmatch(r'[0-9a-f]{64}',options.expected_executable_sha256) is None
            or identity_before['executable_sha256']!=options.expected_executable_sha256):
        raise NativeRoleError('Gemini executable differs from frozen launcher pin')
    metadata = dict(identity_before)
    response_contract = response_contract_from_request(request)
    response_contract_path = options.output_dir / 'role-response-schema.json'
    contract_bytes = canonical(response_contract)
    if response_contract_path.exists():
        if _read(response_contract_path) != contract_bytes:
            raise NativeRoleError('bound output schema changed')
    else: _write(response_contract_path, response_contract)
    metadata['response_schema_sha256'] = digest(contract_bytes)
    metadata['response_schema_scope'] = 'Prompt guidance and strict local validation only; no provider enforcement claim'
    catalog_metadata = {}; catalog_path = None
    if options.provider == "codex":
        if options.codex_reasoning_effort is None:
            raise NativeRoleError("Codex role requires an explicit --codex-reasoning-effort")
        if options.model_catalog is None: raise NativeRoleError("Codex role requires a pinned public model catalog")
        public = _read(options.model_catalog)
        normalized_source = strict(public.decode())
        projected = role_model_catalog(normalized_source, options.model)
        # Validate the requested effort against the selected model's projected
        # public catalog's supported_reasoning_levels (entries .effort). This
        # does not claim the remote server honors the value, only that the
        # public catalog lists it as a supported option for this model.
        supported = projected["models"][0].get("supported_reasoning_levels", [])
        if type(supported) is not list or not any(
                isinstance(entry, dict) and entry.get("effort") == options.codex_reasoning_effort
                for entry in supported):
            raise NativeRoleError(
                f"Codex model {options.model!r} public catalog does not list reasoning effort "
                f"{options.codex_reasoning_effort!r} in supported_reasoning_levels")
        normalized = canonical(projected)
        catalog_path = options.output_dir / "runtime-model-catalog.json"
        if catalog_path.exists():
            if _read(catalog_path) != normalized: raise NativeRoleError("runtime model catalog changed")
        else: _write(catalog_path, strict(normalized.decode()))
        catalog_metadata = {"public_model_catalog_sha256": digest(public),
                            "runtime_model_catalog_sha256": digest(normalized),
                            "tool_surface_override": "direct; no shell, patch, search or experimental tools",
                            "requested_reasoning_effort": options.codex_reasoning_effort,
                            "effective_remote_reasoning_effort": "not observed"}
    elif options.codex_reasoning_effort is not None:
        raise NativeRoleError("Gemini provider does not accept --codex-reasoning-effort")
    elif options.model_catalog is not None: raise NativeRoleError("model catalog is only supported for Codex")
    args = native_argv(options.provider, options.model, prompt,
                       model_catalog=catalog_path,
                       reasoning_effort=options.codex_reasoning_effort)
    if identity_before != execution_identity(options.provider, executable):
        raise NativeRoleError("provider configuration/executable changed before dispatch")
    payload = (canonical({'event': 'user', 'message': {'role': 'user',
               'content': [{'type': 'text', 'text': prompt}]}}) + b'\n') if options.provider == 'gemini' else prompt.encode()
    environment = dict(os.environ)
    metadata = {**metadata, **catalog_metadata}
    store = JobStore(options.output_dir / "native", max_jobs=2)
    if options.provider == "codex":
        preflight = store.execute("configuration-check", codex_feature_argv(args),
                                 {"purpose": "native feature restriction check, no model call"},
                                 cwd=Path.cwd(), timeout_seconds=10, env=environment, metadata=metadata)
        measured = preflight["receipt"]
        if measured["exit_code"] != 0 or measured["timed_out"] or measured["truncated_streams"]:
            raise NativeRoleError("native feature preflight inconclusive")
        metadata = {**metadata, "effective_features": validate_codex_features(preflight["stdout"].decode())}
    job = store.execute("call", args, {"provider": options.provider, "model": options.model},
                        cwd=Path.cwd(), timeout_seconds=180, stdin_bytes=payload,
                        env=environment, metadata=metadata)
    receipt = job["receipt"]
    if (receipt["exit_code"] != 0 or receipt["timed_out"] or receipt["truncated_streams"]
            or receipt.get("stdin_complete") is False):
        raise NativeRoleError("native process failed, timed out, truncated or could not receive full input")
    native_reconnections = []
    response, usage = (parse_gemini_stream(job["stdout"].decode()) if options.provider == 'gemini'
                       else parse_native(options.provider, job["stdout"].decode(), diagnostics=native_reconnections))
    if identity_before != execution_identity(options.provider, args[0]):
        raise NativeRoleError("provider configuration/executable changed during execution")
    if catalog_path is not None and (digest(_read(catalog_path)) != catalog_metadata["runtime_model_catalog_sha256"]
            or digest(_read(options.model_catalog)) != catalog_metadata["public_model_catalog_sha256"]):
        raise NativeRoleError("model catalog changed during execution")
    validate_result(response, request["role"], author_format=requested_author_format)
    if response_contract_path is not None:
        if digest(_read(response_contract_path)) != metadata['response_schema_sha256']:
            raise NativeRoleError('bound output schema changed during execution')
        from specorganon.native_response_contract import validate_response_schema
        validate_response_schema(response, response_contract)
    print(json.dumps({"schema": 1, "provider": options.provider, "model": options.model,
                      "request_sha256": digest(raw), "invocation_metadata": metadata,
                      "native_exit_code": receipt["exit_code"], "usage_reported": usage,
                      "native_reconnections": native_reconnections,
                      "result": response}, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    try: main()
    except (NativeRoleError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"native role inconclusive: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
