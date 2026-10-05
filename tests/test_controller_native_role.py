"""Parser fixtures, not actual provider invocations or independent approvals."""
import json
from pathlib import Path

import pytest

from scripts.controller_native_role import NativeRoleError, native_argv, parse_native, response_json
from specorganon.role_jobs import digest


def test_gemini_role_documents_are_sent_on_stdin_not_exposed_in_argv():
    prompt = 'PUBLIC_UNTRUSTED_DOCUMENT_MARKER_20261005'
    argv = native_argv('gemini', 'gemini-3.1-pro-high', prompt)
    assert prompt not in argv
    assert argv[-3:] == ['--input-format', 'stream-json', '--print=']


def test_actual_gemini_stdin_stream_transport_stays_semantically_inconclusive():
    from scripts.controller_native_role import parse_gemini_stream
    from pathlib import Path
    raw = Path('goals/autonomous-software-v1/evidence/gemini-stream-surface-03-native.stdout.jsonl').read_text()
    result, usage = parse_gemini_stream(raw)
    assert result['verdict'] == 'inconclusive' and result['nonce'] == 'gemini-stream-20261005-v3'
    assert usage['total_tokens'] == 13147


@pytest.mark.parametrize('fault', ['tool', 'duplicate_turn', 'wrong_text', 'after_result', 'malformed_step'])
def test_gemini_stream_refuses_tool_or_unbound_completion(fault):
    from scripts.controller_native_role import parse_gemini_stream
    from pathlib import Path
    import json
    events = [json.loads(line) for line in Path('goals/autonomous-software-v1/evidence/gemini-stream-surface-03-native.stdout.jsonl').read_text().splitlines()]
    if fault == 'tool': events[2]['step_update']['step_type'] = 'run_command'
    elif fault == 'duplicate_turn': events.insert(2, events[1])
    elif fault == 'wrong_text': events[-1]['result']['response'] = '{"verdict":"accept"}'
    elif fault == 'after_result': events.append(events[-1])
    else: events[2]['step_update']['step_type'] = []
    with pytest.raises(NativeRoleError): parse_gemini_stream('\n'.join(json.dumps(v) for v in events))


def test_gemini_native_usage_is_preserved_and_missing_usage_stays_unknown():
    value = {"status": "SUCCESS", "response": '{"verdict":"reject","reason":"insufficient evidence"}'}
    response, usage = parse_native("gemini", json.dumps(value))
    assert response["verdict"] == "reject" and usage is None
    value["usage"] = {"input_tokens": 5, "output_tokens": 3, "cache_read_tokens": 2}
    assert parse_native("gemini", json.dumps(value))[1] == value["usage"]


@pytest.mark.parametrize("change", ["denied", "empty", "failed"])
def test_success_exit_label_cannot_hide_denial_or_empty_response(change):
    value = {"status": "SUCCESS", "response": '{"verdict":"accept"}'}
    if change == "denied": value["denied_actions"] = [{"action": "command"}]
    elif change == "empty": value["response"] = ""
    else: value["status"] = "FAILED"
    with pytest.raises(NativeRoleError): parse_native("gemini", json.dumps(value))


def test_codex_requires_completed_turn_and_rejects_tool_calls():
    events = codex_transcript()
    with pytest.raises(NativeRoleError): parse_native("codex", json.dumps(events[2]))
    assert parse_native("codex", "\n".join(map(json.dumps, events))) == ({"verdict": "reject"}, {"input_tokens": 12})
    events.insert(2, {"type": "item.started", "item": {"type": "command_execution"}})
    with pytest.raises(NativeRoleError, match="tool"): parse_native("codex", "\n".join(map(json.dumps, events)))


@pytest.mark.parametrize("text", ['{"value":736.00000000000000001}', '{"verdict":"accept","verdict":"reject"}',
                                 '{"value":NaN}', 'Narrative before {"verdict":"accept"}'])
def test_bridge_cannot_round_duplicate_or_extract_a_fake_final_json(text):
    with pytest.raises(NativeRoleError): response_json(text)


def test_codex_runtime_override_uses_cli_literal_safe_key_not_quoted_table(tmp_path, monkeypatch):
    # Synthetic config only: no real profile, session or credentials are copied.
    (tmp_path / "config.toml").write_text('[mcp_servers.specorganon]\ncommand="fake-fixture"\n')
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    args = native_argv("codex", "gpt-6.1-sol", "fixture text", reasoning_effort="low")
    assert "mcp_servers.specorganon.enabled=false" in args


def test_non_literal_mcp_key_stops_before_native_launch(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text('[mcp_servers."unsafe.name"]\ncommand="fake-fixture"\n')
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    with pytest.raises(NativeRoleError, match="key"):
        native_argv("codex", "gpt-6.1-sol", "fixture text", reasoning_effort="low")


def codex_transcript():
    return [
        {"type": "thread.started", "thread_id": "synthetic-thread"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": '{"verdict":"reject"}'}},
        {"type": "turn.completed", "usage": {"input_tokens": 12}},
    ]


@pytest.mark.parametrize("mutation", ["unknown", "second_turn", "early_completion", "after_completion",
                                      "malformed_item", "multiple_answers", "unmatched_update"])
def test_codex_event_state_machine_rejects_unassociated_or_unknown_output(mutation):
    events = codex_transcript()
    if mutation == "unknown": events.insert(2, {"type": "provider.unknown", "item": {"type": "command_execution"}})
    elif mutation == "second_turn": events += events[1:]
    elif mutation == "early_completion": events[1], events[-1] = events[-1], events[1]
    elif mutation == "after_completion": events.append(events[2])
    elif mutation == "malformed_item": events[2]["item"] = []
    elif mutation == "multiple_answers":
        events.insert(3, {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": '{"verdict":"accept"}'}})
    else: events.insert(2, {"type": "item.updated", "item": {"id": "item_x", "type": "reasoning", "text": "unstarted"}})
    with pytest.raises(NativeRoleError): parse_native("codex", "\n".join(map(json.dumps, events)))


@pytest.mark.parametrize("value", [[], {"role_instructions": 5}, {"role_instructions": ""},
                                     {"role_instructions": "review", "unexpected": "value"}])
def test_request_schema_is_checked_before_rendering(value):
    from scripts.controller_native_role import render_prompt
    with pytest.raises(NativeRoleError): render_prompt(json.dumps(value).encode())


def test_bounded_request_reader_rejects_large_files_and_symlinks(tmp_path):
    from scripts.controller_native_role import read_request
    path = tmp_path / "request.json"; path.write_bytes(b"x" * 128001)
    with pytest.raises(NativeRoleError): read_request(path)
    path.unlink(); path.symlink_to(tmp_path / "absent")
    with pytest.raises(NativeRoleError): read_request(path)


def test_requested_review_result_contract_is_checked():
    from scripts.controller_native_role import validate_result
    assert validate_result({"schema": 1, "verdict": "reject", "reason": "actual finding", "findings": []}, "review")["verdict"] == "reject"
    for value in [{}, {"schema": 1, "verdict": "accept", "reason": "", "findings": []},
                  {"schema": 1, "verdict": "magic", "reason": "finding", "findings": []},
                  {"schema": 1, "verdict": "accept", "reason": "finding", "findings": "missing"},
                  {"schema": 1, "verdict": "accept", "reason": "textual accept is not admission", "findings": ["praise"]},
                  {"schema": 1, "verdict": "accept", "reason": "empty finding", "findings": [{}]}]:
        with pytest.raises(NativeRoleError): validate_result(value, "review")


def test_complete_request_and_nested_numbers_round_trip_exactly():
    from scripts.controller_native_role import render_prompt
    request = {"schema": 1, "role": "review", "role_instructions": "Judge supplied data only", "documents": {"sample": "actual sample"}}
    parsed, prompt = render_prompt(json.dumps(request).encode())
    assert parsed == request and "actual sample" in prompt
    value = response_json('{"nested":[{"decimal":0.1,"integer":9007199254740993}]}')
    assert response_json(json.dumps(value)) == value
    with pytest.raises(NativeRoleError): response_json('{"nested":[{"decimal":1e-400}]}')


def test_execution_identity_requires_pinned_image_and_binds_nonsecret_config(tmp_path, monkeypatch):
    from scripts.controller_native_role import execution_identity
    exe = tmp_path / "native"; exe.write_bytes(b"synthetic executable")
    monkeypatch.delenv("SPECORGANON_ROLE_IMAGE_ID", raising=False)
    with pytest.raises(NativeRoleError, match="image"): execution_identity("codex", str(exe))
    monkeypatch.setenv("SPECORGANON_ROLE_IMAGE_ID", "sha256:" + "a" * 64)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    config = tmp_path / "config.toml"; config.write_text('model="synthetic"')
    identity = execution_identity("codex", str(exe))
    config.write_text('model="changed"')
    assert identity != execution_identity("codex", str(exe))
    assert "other_effective_configuration" in identity


def test_observed_codex_0160_native_review_transcript_preserves_real_rejection():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    evidence = root / "goals/autonomous-software-v1/evidence"
    raw = (evidence / "component-review-03-native.stdout.jsonl").read_text()
    result, usage = parse_native("codex", raw)
    recorded = json.loads((evidence / "component-review-03.stdout.json").read_text())
    assert result == recorded["result"] and usage == recorded["usage_reported"]
    assert result["verdict"] == "reject" and result["tests_executed"] is False


def test_actual_effective_catalogue_controls_shell_registration_not_backend_flag():
    from pathlib import Path
    from scripts.controller_native_role import validate_codex_features
    root = Path(__file__).resolve().parents[1]
    raw = (root / 'goals/autonomous-software-v1/evidence/controller-codex-effective-features.stdout').read_text()
    measured = validate_codex_features(raw)
    assert measured['unified_exec_observed'] is True
    assert measured['complete_configuration_isolation'] is False
    with pytest.raises(NativeRoleError): validate_codex_features(raw.replace('shell_tool                               stable             false', 'shell_tool                               stable             true'))


def test_effective_feature_probe_uses_same_overrides_without_native_exec_command(tmp_path, monkeypatch):
    from scripts.controller_native_role import codex_feature_argv
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    native = native_argv('codex', 'gpt-6.1-sol', 'fixture', reasoning_effort='low')
    probe = codex_feature_argv(native)
    assert probe[-2:] == ['features', 'list'] and 'exec' not in probe
    assert 'web_search="disabled"' in probe and 'shell_tool' in probe


@pytest.mark.parametrize('bad', [[], {}])
def test_malformed_role_and_verdict_have_controlled_schema_error(bad):
    from scripts.controller_native_role import render_prompt, validate_result
    request = {'schema': 1, 'role': bad, 'role_instructions': 'review', 'documents': {}}
    with pytest.raises(NativeRoleError): render_prompt(json.dumps(request).encode())
    value = {'schema': 1, 'verdict': bad, 'reason': 'finding', 'findings': []}
    with pytest.raises(NativeRoleError): validate_result(value, 'review')


@pytest.mark.parametrize('bad', [[], {}])
def test_malformed_event_type_is_a_controlled_native_error(bad):
    with pytest.raises(NativeRoleError): parse_native('codex', json.dumps({'type': bad}))


def test_actual_native_startup_error_keeps_followup_inconclusive():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    evidence = root / 'goals/autonomous-software-v1/evidence'
    raw = (evidence / 'component-review-04-native-call.stdout.jsonl').read_text()
    with pytest.raises(NativeRoleError): parse_native('codex', raw)
    text = json.loads((evidence / 'component-review-04-textual-verdict.json').read_text())
    assert text['verdict'] == 'reject' and text['tests_executed'] is False


def test_public_model_catalog_normalizes_only_role_tool_surface():
    from scripts.controller_native_role import role_model_catalog
    original = {'slug': 'gpt-6.1-sol', 'description': 'fixture model', 'tool_mode': 'code_mode_only',
                'shell_type': 'unified_exec', 'apply_patch_tool_type': 'freeform',
                'experimental_supported_tools': ['fake_tool'], 'supports_search_tool': True, 'web_search_tool_type': 'text'}
    result = role_model_catalog({'models': [original]}, 'gpt-6.1-sol')
    model = result['models'][0]
    assert model['slug'] == original['slug'] and model['description'] == original['description']
    assert original['tool_mode'] == 'code_mode_only'
    assert model['tool_mode'] == 'direct' and model['shell_type'] == 'disabled'
    assert model['apply_patch_tool_type'] is None and model['experimental_supported_tools'] == []
    assert model['supports_search_tool'] is False and model['web_search_tool_type'] == original['web_search_tool_type']
    with pytest.raises(NativeRoleError): role_model_catalog({'models': [original, original]}, original['slug'])
    with pytest.raises(NativeRoleError): role_model_catalog({'models': [original]}, 'not-catalogued')


def test_model_catalog_override_is_bound_to_same_preflight_and_native_request(tmp_path, monkeypatch):
    from scripts.controller_native_role import codex_feature_argv
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    catalog = tmp_path / 'catalog.json'
    args = native_argv('codex', 'gpt-6.1-sol', 'fixture', model_catalog=catalog, reasoning_effort='low')
    override = 'model_catalog_json=' + json.dumps(str(catalog))
    assert override in args and override in codex_feature_argv(args)


def test_actual_restricted_catalog_native_transport_stays_semantically_inconclusive():
    from pathlib import Path
    e = Path(__file__).resolve().parents[1] / 'goals/autonomous-software-v1/evidence'
    result, usage = parse_native('codex', (e / 'native-surface-01-native-call.stdout.jsonl').read_text())
    assert result['verdict'] == 'inconclusive' and result['nonce'] == 'native-surface-v1-20261005'
    assert usage == json.loads((e / 'native-surface-01-receipt.json').read_text())['usage_reported']


def test_codex_native_argv_requires_explicit_bounded_reasoning_effort():
    with pytest.raises(NativeRoleError, match="reasoning effort"):
        native_argv("codex", "gpt-6.1-sol", "fixture")
    with pytest.raises(NativeRoleError, match="reasoning effort"):
        native_argv("codex", "gpt-6.1-sol", "fixture", reasoning_effort=None)


@pytest.mark.parametrize("bad", ["min", "max", "ultra", "default", "", "LOW"])
def test_codex_native_argv_rejects_out_of_set_reasoning_effort(bad):
    with pytest.raises(NativeRoleError, match="reasoning effort"):
        native_argv("codex", "gpt-6.1-sol", "fixture", reasoning_effort=bad)


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh"])
def test_codex_native_argv_emits_model_reasoning_effort_override(tmp_path, monkeypatch, effort):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    args = native_argv("codex", "gpt-6.1-sol", "fixture", reasoning_effort=effort)
    assert f'model_reasoning_effort="{effort}"' in args


def test_gemini_native_argv_rejects_explicit_reasoning_effort():
    with pytest.raises(NativeRoleError, match="Gemini"):
        native_argv("gemini", "gemini-3.1-pro-high", "fixture", reasoning_effort="low")


def test_explicit_low_override_leaves_synthetic_profile_bytes_unchanged(tmp_path, monkeypatch):
    # Synthetic high-effort profile: CLI override must not rewrite profile bytes
    # on disk; it is only a dotted -c override that travels inside argv.
    config = tmp_path / "config.toml"
    original_bytes = b'model_reasoning_effort = "high"\n'
    config.write_bytes(original_bytes)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    args = native_argv("codex", "gpt-6.1-sol", "fixture", reasoning_effort="low")
    assert config.read_bytes() == original_bytes
    assert 'model_reasoning_effort="low"' in args
    # The original on-disk entry remains as written (no profile mutation).
    assert b'model_reasoning_effort = "high"' in config.read_bytes()


def _stub_identity(monkeypatch):
    """Bypass execution_identity() file resolution so main() can be exercised
    without the real /usr/local/bin/codex executable."""
    monkeypatch.setenv("SPECORGANON_ROLE_IMAGE_ID", "sha256:" + "a" * 64)
    from scripts.controller_native_role import execution_identity
    def _fake(provider, executable, _real=execution_identity):
        return _real(provider, executable) if Path(executable).exists() else {
            "schema": 1, "image_id": "sha256:" + "a" * 64,
            "executable_path": executable, "executable_sha256": digest(b"synthetic"),
            "known_configuration_path": str(Path(executable).parent / "config.toml"),
            "known_configuration_sha256": None,
            "other_effective_configuration": "unknown; trusted launcher/profile boundary"}
    monkeypatch.setattr("scripts.controller_native_role.execution_identity", _fake)


def test_native_role_main_rejects_missing_effort_for_codex_before_native_launch(tmp_path, monkeypatch):
    from scripts.controller_native_role import main
    _stub_identity(monkeypatch)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"schema": 1, "role": "review", "role_instructions": "fixture",
                                    "documents": {}}))
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"models": [{"slug": "gpt-6.1-sol",
        "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}]}]}))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    with pytest.raises(NativeRoleError, match="--codex-reasoning-effort"):
        main(["--provider", "codex", "--model", "gpt-6.1-sol",
              "--request", str(request), "--output-dir", str(tmp_path / "out"),
              "--model-catalog", str(catalog)])


def test_native_role_main_rejects_effort_for_gemini_before_native_launch(tmp_path, monkeypatch):
    from scripts.controller_native_role import main
    _stub_identity(monkeypatch)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"schema": 1, "role": "review", "role_instructions": "fixture",
                                    "documents": {}}))
    with pytest.raises(NativeRoleError, match="Gemini"):
        main(["--provider", "gemini", "--model", "gemini-3.1-pro-high",
              "--request", str(request), "--output-dir", str(tmp_path / "out"),
              "--codex-reasoning-effort", "low"])


def test_native_role_main_rejects_unsupported_catalog_reasoning_level(tmp_path, monkeypatch):
    from scripts.controller_native_role import main
    _stub_identity(monkeypatch)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"schema": 1, "role": "review", "role_instructions": "fixture",
                                    "documents": {}}))
    # Catalog lists low/medium but not high for this model.
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"models": [{"slug": "fixture-model",
        "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}]}]}))
    with pytest.raises(NativeRoleError, match="supported_reasoning_levels"):
        main(["--provider", "codex", "--model", "fixture-model",
              "--request", str(request), "--output-dir", str(tmp_path / "out"),
              "--model-catalog", str(catalog),
              "--codex-reasoning-effort", "high"])
