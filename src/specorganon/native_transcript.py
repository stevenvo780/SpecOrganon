"""Exact text-only native transcript/feature/body checks shared with host custody.

No invocation, configuration, credential or filesystem access. Parsing a closed
transcript does not establish semantic truth or comparative effectiveness.
"""
from __future__ import annotations
import re
from .ledger import strict_json_loads
from .role_jobs import digest
from .native_response_contract import CODEX_TEXT_ONLY_DISABLED

class NativeRoleError(ValueError):
    pass

def strict(raw):
    try: return strict_json_loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise NativeRoleError("invalid exact finite JSON") from exc


def response_json(text):
    if type(text) is not str or not text.strip(): raise NativeRoleError("empty role response")
    value = strict(text)
    if type(value) is not dict: raise NativeRoleError("role response must be one JSON object")
    return value


def parse_gemini_stream(raw):
    """Observed AGY stream-json: one user/agent turn, no tool/unknown events."""
    state = 'initial'; conversation = None; text = ''; agent_done = False; user_seen = False
    for line in raw.splitlines():
        if not line.strip(): continue
        value = strict(line)
        if type(value) is not dict or type(value.get('event')) is not str:
            raise NativeRoleError('invalid Gemini stream event')
        event = value['event']
        if event == 'init' and state == 'initial':
            if (set(value) != {'event', 'conversation_id', 'init'} or type(value['conversation_id']) is not str
                    or not value['conversation_id'] or type(value['init']) is not dict):
                raise NativeRoleError('invalid Gemini stream initialization')
            conversation = value['conversation_id']; state = 'turn'
        elif event == 'step_update' and state == 'turn':
            step = value.get('step_update')
            if (set(value) != {'event', 'step_update'} or type(step) is not dict
                    or step.get('conversation_id') != conversation or type(step.get('step_index')) is not int
                    or type(step.get('step_type')) is not str or type(step.get('state')) is not str):
                raise NativeRoleError('invalid Gemini stream step')
            if step['step_type'] == 'user_input':
                if (user_seen or step['step_index'] != 0 or step['state'] != 'DONE'
                        or set(step) != {'conversation_id', 'step_index', 'state', 'step_type'}):
                    raise NativeRoleError('unexpected Gemini stream user turn')
                user_seen = True
            elif step['step_type'] == 'agent_response':
                if (not user_seen or agent_done or step['step_index'] != 1 or step['state'] not in {'ACTIVE', 'DONE'}
                        or type(step.get('text_delta')) is not str
                        or not set(step) <= {'conversation_id', 'step_index', 'state', 'step_type',
                                            'text_delta', 'duration_seconds', 'usage'}):
                    raise NativeRoleError('unexpected Gemini stream response')
                text += step['text_delta']; agent_done = step['state'] == 'DONE'
            else: raise NativeRoleError('text-only Gemini role invoked a tool or unknown step')
        elif event == 'result' and state == 'turn':
            result = value.get('result')
            if (set(value) != {'event', 'result'} or type(result) is not dict or not agent_done
                    or result.get('conversation_id') != conversation or result.get('status') != 'SUCCESS'
                    or result.get('error') or result.get('denied_actions')
                    or type(result.get('num_turns')) is not int or result['num_turns'] != 1
                    or result.get('response') != text or not text.strip()):
                raise NativeRoleError('Gemini stream did not close its exact single text turn')
            final = response_json(text); usage = result.get('usage'); state = 'complete'
        else: raise NativeRoleError('unknown or unordered Gemini stream event')
    if state != 'complete': raise NativeRoleError('incomplete Gemini native stream')
    return final, usage


def parse_native(provider, raw, *, diagnostics=None):
    if provider == "gemini":
        value = strict(raw)
        if type(value) is not dict or value.get("status") != "SUCCESS" or value.get("denied_actions"):
            raise NativeRoleError("native Gemini execution failed or permission was denied")
        return response_json(value.get("response")), value.get("usage")
    if provider != "codex": raise NativeRoleError("unsupported provider")
    # Fail closed for this observed Codex 0.160.0 JSONL format. Future native
    # event formats require a reviewed adapter version, not silent skipping.
    final = None; usage = None; state = "initial"; items = {}; reconnects = []
    for line in raw.splitlines():
        if not line.strip(): continue
        value = strict(line)
        if type(value) is not dict: raise NativeRoleError("native Codex event must be an object")
        kind = value.get("type")
        if type(kind) is not str: raise NativeRoleError("invalid native event type")
        if kind == 'turn.failed': raise NativeRoleError('native Codex turn failed')
        if kind == 'error':
            # Observed 0.160.0 emits this exact progress shape during its OWN
            # reconnection, then can close the SAME turn with one final message.
            # Never treat an arbitrary error, terminal failure or incomplete
            # turn as success, and never launch another process/model request.
            message = value.get('message')
            match = re.fullmatch(r'Reconnecting\.\.\. ([1-5])/5 \([^\r\n]+\)', message) if type(message) is str else None
            if (state != 'turn' or final is not None or set(value) != {'type', 'message'}
                    or not match or reconnects and int(match[1]) <= reconnects[-1]['attempt']):
                raise NativeRoleError('native Codex turn failed')
            reconnects.append({'attempt': int(match[1]), 'limit': 5,
                              'message_sha256': digest(message.encode())})
            continue
        if kind == "thread.started" and state == "initial":
            if set(value) != {"type", "thread_id"} or type(value["thread_id"]) is not str or not value["thread_id"]:
                raise NativeRoleError("invalid native thread event")
            state = "thread"
        elif kind == "turn.started" and state == "thread" and set(value) == {"type"}:
            state = "turn"
        elif kind in {"item.started", "item.updated", "item.completed"} and state == "turn":
            item = value.get("item")
            if type(item) is not dict or set(value) != {"type", "item"}:
                raise NativeRoleError("invalid native item event")
            if type(item.get("type")) is not str or item.get("type") not in {"agent_message", "reasoning"}:
                raise NativeRoleError("text-only role invoked a tool")
            if (set(item) != {"id", "type", "text"} or type(item["id"]) is not str or not item["id"]
                    or type(item["text"]) is not str):
                raise NativeRoleError("invalid native text item")
            previous = items.get(item["id"])
            if (previous is not None and (previous[0] == "item.completed" or previous[1] != item["type"])
                    or kind == "item.started" and previous is not None
                    or kind == "item.updated" and previous is None):
                raise NativeRoleError("unordered native item events")
            items[item["id"]] = (kind, item["type"])
            if kind == "item.completed" and item["type"] == "agent_message":
                if final is not None: raise NativeRoleError("multiple native final messages")
                final = item["text"]
        elif kind == "turn.completed" and state == "turn":
            if (set(value) != {"type", "usage"} or type(value["usage"]) is not dict
                    or final is None or any(event[0] != "item.completed" for event in items.values())):
                raise NativeRoleError("invalid native completion")
            state = "complete"; usage = value["usage"]
        else:
            raise NativeRoleError("unknown or unordered native event")
    if state != "complete": raise NativeRoleError("native Codex response is incomplete")
    response = response_json(final)
    if diagnostics is not None:
        diagnostics.extend(reconnects)
    return response, usage


def validate_codex_features(raw):
    values = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[-1] not in {"true", "false"} or fields[0] in values:
            raise NativeRoleError("invalid native effective feature catalogue")
        values[fields[0]] = fields[-1] == "true"
    if any(values.get(name) is not False for name in CODEX_TEXT_ONLY_DISABLED):
        raise NativeRoleError("native text-only feature restriction not effective")
    # In 0.160.0 unified_exec is normalized to true for ordinary user settings.
    # spec_plan.rs does not register shell tools when ShellTool is disabled.
    # Preserve its observed value; do not claim the flag was turned off.
    return {"disabled_features": CODEX_TEXT_ONLY_DISABLED, "unified_exec_observed": values.get("unified_exec"),
            "shell_registration_control": "shell_tool=false; Codex 0.160.0 spec_plan.rs",
            "complete_configuration_isolation": False}


def validate_result(value, role, *, author_format='manifest-v1'):
    if type(value) is not dict or type(value.get("schema")) is not int or value.get("schema") != 1:
        raise NativeRoleError("invalid role result schema")
    if role == "review":
        if (value.get('tests_executed') is not False
                or type(value.get("verdict")) is not str or value.get("verdict") not in {"accept", "reject", "inconclusive"}
                or type(value.get("reason")) is not str or not value["reason"].strip()
                or type(value.get("findings")) is not list
                or any(type(f) is not dict or not f for f in value["findings"])):
            raise NativeRoleError("invalid review result contract")
    elif role == "author":
        if author_format == 'files-v1':
            from specorganon.neutral_author import neutral_author_content
            try: return neutral_author_content(value)
            except ValueError as exc: raise NativeRoleError('invalid neutral author content contract') from exc
        if author_format == 'items-v1':
            from specorganon.author_contract import typed_author_manifest
            try: typed_author_manifest(value)
            except ValueError as exc: raise NativeRoleError('invalid typed author content contract') from exc
            return value
        if author_format != 'manifest-v1': raise NativeRoleError('unsupported author response format')
        if (set(value) != {"schema", "manifest", "files", "reason"}
                or type(value["manifest"]) is not dict or type(value["files"]) is not dict
                or type(value["reason"]) is not str or not value["reason"].strip()
                or any(type(k) is not str or type(v) is not str for k, v in value["files"].items())):
            raise NativeRoleError("invalid author result contract")
    else: raise NativeRoleError("unsupported role result contract")
    return value

