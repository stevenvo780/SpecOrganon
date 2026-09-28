"""Development-only Responses dispatcher with a pre-send shared reservation.

This path sends one request at a time. Input may include plain messages,
prior Responses reasoning/message output items, and bounded function-call
replay with strictly declared functions. It does not execute tools, accept
multimodal parts, manage an agent conversation, enforce time limits, or
make a CLI opaque to the caller safe for a confirmatory study. The caller must
use one ledger directory for every request and agent in the same run. Provider
calls require an explicit CLI flag and an API key; tests use a fake transport.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

from managed_token_ledger import BudgetError, TokenLedger


MAX_JSON_BYTES = 16 * 1024 * 1024
REQUEST_KEYS = frozenset({
    "model", "input", "instructions", "reasoning", "max_output_tokens", "service_tier",
    "tools", "parallel_tool_calls",
})
FUNCTION_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
PRIMITIVE_TYPES = frozenset({"string", "integer", "number", "boolean"})


class DispatchError(ValueError):
    """A request or provider result cannot be accepted as a measured dispatch."""


class ResponseTransport(Protocol):
    def count_input(self, payload: dict[str, Any]) -> int: ...
    def send(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise DispatchError("request contains invalid JSON") from exc


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DispatchError("JSON contains a duplicate key")
        value[key] = item
    return value


def _reject_constant(_value: str) -> None:
    raise DispatchError("JSON contains a nonfinite number")


def _parse_exact_float(raw: str) -> float:
    """Reject JSON decimals that would change value when passed as a float."""
    try:
        value = float(raw)
        original = Decimal(raw)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise DispatchError("JSON decimal loses precision as a float") from exc
    if not math.isfinite(value) or Decimal(str(value)) != original:
        raise DispatchError("JSON decimal loses precision as a float")
    return value


def _read_json_file(path: Path) -> Any:
    raw = path.read_bytes()
    if len(raw) > MAX_JSON_BYTES:
        raise DispatchError("JSON file exceeds the byte limit")
    return json.loads(raw, object_pairs_hook=_unique_pairs,
                      parse_constant=_reject_constant)


def _validate_function_tool(tool: Any) -> None:
    if (type(tool) is not dict
            or set(tool) != {"type", "name", "description", "parameters", "strict"}
            or tool["type"] != "function" or tool["strict"] is not True
            or type(tool["name"]) is not str
            or FUNCTION_NAME.fullmatch(tool["name"]) is None
            or type(tool["description"]) is not str
            or not tool["description"].strip()):
        raise DispatchError("tools must be strict custom function definitions")
    schema = tool["parameters"]
    if (type(schema) is not dict
            or set(schema) != {"type", "properties", "required", "additionalProperties"}
            or schema["type"] != "object"
            or schema["additionalProperties"] is not False
            or type(schema["properties"]) is not dict
            or type(schema["required"]) is not list):
        raise DispatchError("function parameters must be a closed object schema")
    properties = schema["properties"]
    required = schema["required"]
    if (any(type(name) is not str or FUNCTION_NAME.fullmatch(name) is None
            for name in properties)
            or any(type(name) is not str for name in required)
            or len(required) != len(properties) or set(required) != set(properties)):
        raise DispatchError("function required must name every property exactly once")
    for field in properties.values():
        if (type(field) is not dict
                or set(field) not in ({"type"}, {"type", "description"})
                or type(field["type"]) is not str
                or field["type"] not in PRIMITIVE_TYPES
                or "description" in field
                and (type(field["description"]) is not str
                     or not field["description"].strip())):
            raise DispatchError("function properties must use primitive types")


def _parse_function_arguments(tool: dict, raw: str) -> dict:
    """Parse a function call as strict JSON matching its closed primitive schema."""
    _validate_function_tool(tool)
    if type(raw) is not str:
        raise DispatchError("function arguments must be bounded JSON text")
    try:
        raw_size = len(raw.encode("utf-8"))
    except UnicodeError as exc:
        raise DispatchError("function arguments are invalid JSON text") from exc
    if raw_size > MAX_JSON_BYTES:
        raise DispatchError("function arguments must be bounded JSON text")
    try:
        arguments = json.loads(raw, object_pairs_hook=_unique_pairs,
                               parse_constant=_reject_constant,
                               parse_float=_parse_exact_float)
    except DispatchError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise DispatchError("function arguments are invalid JSON") from exc
    properties = tool["parameters"]["properties"]
    if type(arguments) is not dict or set(arguments) != set(properties):
        raise DispatchError("function arguments must match the declared properties")
    for name, field in properties.items():
        value = arguments[name]
        kind = field["type"]
        valid = (type(value) is str if kind == "string" else
                 type(value) is int if kind == "integer" else
                 type(value) is int or type(value) is float and math.isfinite(value)
                 if kind == "number" else type(value) is bool)
        if not valid:
            raise DispatchError(f"function argument {name} has the wrong type")
    return arguments


def _validated_request(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict or not {"model", "input", "max_output_tokens"} <= raw.keys() \
            or not raw.keys() <= REQUEST_KEYS:
        raise DispatchError("request has missing or unsupported fields")
    if type(raw["model"]) is not str or not raw["model"].strip():
        raise DispatchError("model must be a nonempty string")
    if type(raw["input"]) not in (str, list) or not raw["input"]:
        raise DispatchError("input must be nonempty text or a message array")
    functions: dict[str, dict] = {}
    if "tools" in raw:
        tools = raw["tools"]
        if type(tools) is not list or not 1 <= len(tools) <= 8:
            raise DispatchError("tools must contain one to eight functions")
        if raw.get("parallel_tool_calls") is not False:
            raise DispatchError("tools require parallel_tool_calls false")
        for tool in tools:
            _validate_function_tool(tool)
            if tool["name"] in functions:
                raise DispatchError("function names must be unique")
            functions[tool["name"]] = tool
    elif "parallel_tool_calls" in raw:
        raise DispatchError("parallel_tool_calls requires tools")
    if type(raw["input"]) is list:
        pending_call: str | None = None
        seen_calls: set[str] = set()
        for item in raw["input"]:
            if type(item) is not dict:
                raise DispatchError("input array contains a non-object item")
            if pending_call is not None and item.get("type") != "function_call_output":
                raise DispatchError("function call needs its matching output")
            if set(item) == {"role", "content"}:
                if (type(item["role"]) is not str
                        or item["role"] not in {"system", "developer", "user", "assistant"}
                        or type(item["content"]) is not str or not item["content"]):
                    raise DispatchError("message array must contain only text roles and content")
            elif item.get("type") == "reasoning":
                if ("role" in item or type(item.get("encrypted_content")) is not str
                        or not item["encrypted_content"]):
                    raise DispatchError("reasoning item lacks encrypted content")
            elif item.get("type") == "message":
                if (item.get("role") != "assistant"
                        or type(item.get("content")) is not list
                        or not item["content"]):
                    raise DispatchError("output message is not plain assistant text")
                for part in item["content"]:
                    if (type(part) is not dict or part.get("type") != "output_text"
                            or type(part.get("text")) is not str):
                        raise DispatchError("output message contains nontext content")
            elif item.get("type") == "function_call":
                if (not {"type", "name", "arguments", "call_id"} <= set(item)
                        or not set(item) <= {"type", "name", "arguments", "call_id",
                                             "id", "status"}
                        or type(item["name"]) is not str
                        or item["name"] not in functions
                        or type(item["call_id"]) is not str
                        or not item["call_id"] or item["call_id"] in seen_calls
                        or "id" in item and (type(item["id"]) is not str
                                             or not item["id"])
                        or "status" in item and item["status"] != "completed"):
                    raise DispatchError("input contains an unsupported function call")
                _parse_function_arguments(functions[item["name"]], item["arguments"])
                pending_call = item["call_id"]
                seen_calls.add(pending_call)
            elif item.get("type") == "function_call_output":
                if (set(item) != {"type", "call_id", "output"}
                        or type(item["call_id"]) is not str
                        or item["call_id"] != pending_call
                        or type(item["output"]) is not str):
                    raise DispatchError("function output needs a matching call_id and text")
                pending_call = None
            else:
                raise DispatchError("input array contains unsupported item")
        if pending_call is not None:
            raise DispatchError("function call needs its matching output")
    if "instructions" in raw and (type(raw["instructions"]) is not str
                                  or not raw["instructions"]):
        raise DispatchError("instructions must be nonempty text")
    if "reasoning" in raw:
        reasoning = raw["reasoning"]
        if (type(reasoning) is not dict
                or set(reasoning) not in ({"effort"}, {"effort", "context"})
                or type(reasoning["effort"]) is not str
                or reasoning["effort"] not in
                {"none", "low", "medium", "high", "xhigh", "max"}
                or "context" in reasoning
                and (type(reasoning["context"]) is not str
                     or reasoning["context"] not in {"current_turn", "all_turns"})):
            raise DispatchError("reasoning must specify a supported effort")
    if type(raw["max_output_tokens"]) is not int or raw["max_output_tokens"] < 1:
        raise DispatchError("max_output_tokens must be a positive integer")
    if "service_tier" in raw and raw["service_tier"] != "default":
        raise DispatchError("only the explicit default service tier is supported")
    if len(_json_bytes(raw)) > MAX_JSON_BYTES:
        raise DispatchError("request exceeds the byte limit")
    return json.loads(_json_bytes(raw))


def _private_output(path: Path) -> None:
    parent = path.parent
    try:
        info = parent.stat()
    except OSError as exc:
        raise DispatchError("response directory is unavailable") from exc
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700 or path.exists()
            or path.is_symlink()):
        raise DispatchError("response path must be new in a private directory")


def _write_response(path: Path, response: dict[str, Any]) -> str:
    raw = _json_bytes(response) + b"\n"
    if len(raw) > MAX_JSON_BYTES:
        raise DispatchError("provider response exceeds the byte limit")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    finally:
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    return hashlib.sha256(raw).hexdigest()


def dispatch_response(
    ledger: TokenLedger, *, request_id: str, role: str, request: dict[str, Any],
    response_path: Path, transport: ResponseTransport,
) -> dict[str, Any]:
    """Count, reserve, send, preserve, then reconcile one provider response.

    Any uncertain outcome after reservation retains the full reservation. A
    retry requires human review and a new attempt; this function never retries.
    """
    payload = _validated_request(request)
    _private_output(response_path)
    budget_status = ledger.status()
    cost_enabled = budget_status["cost_limit_micro_usd"] is not None
    if cost_enabled:
        if payload.get("service_tier") != "default":
            raise DispatchError("priced requests require the explicit default service tier")
        if budget_status["price_profile"]["model"] != payload["model"]:
            raise DispatchError("request model differs from the frozen price profile")
    count_payload = {key: value for key, value in payload.items()
                     if key not in {"max_output_tokens", "service_tier"}}
    count_bytes = _json_bytes(count_payload)
    input_tokens = transport.count_input(count_payload)
    if type(input_tokens) is not int or input_tokens < 1:
        raise DispatchError("provider input count is missing or invalid")
    if _json_bytes(count_payload) != count_bytes:
        raise DispatchError("input changed during token counting")
    digest = hashlib.sha256(_json_bytes(payload)).hexdigest()
    ledger.reserve(request_id, role, digest, input_tokens,
                   payload["max_output_tokens"], model=payload["model"])
    try:
        provider_payload = {**payload, "store": False, "stream": False}
        response = transport.send(provider_payload)
        if type(response) is not dict:
            raise DispatchError("provider response is not an object")
        response_sha256 = _write_response(response_path, response)
        if (type(response.get("id")) is not str or not response["id"]
                or response.get("model") != payload["model"]
                or response.get("status") not in {"completed", "incomplete"}
                or cost_enabled and response.get("service_tier") != "default"):
            raise DispatchError("provider identity or status is not verifiable")
        usage = response.get("usage")
        measured = ({key: usage.get(key) for key in
                     ("input_tokens", "output_tokens", "total_tokens")}
                    if type(usage) is dict else usage)
        details = ({key: usage[key] for key in
                    ("input_tokens_details", "output_tokens_details") if key in usage}
                   if type(usage) is dict else None)
        settled = ledger.settle(request_id, measured, usage_details=details)
    except Exception as exc:
        try:
            ledger.mark_indeterminate(request_id, type(exc).__name__)
        except BudgetError:
            pass  # settle already made an invalid receipt indeterminate
        raise DispatchError("provider outcome indeterminate; reservation held") from exc
    return {
        "classification": "development_managed_response_unsealed",
        "request_id": request_id,
        "role": role,
        "model_reported": response["model"],
        "provider_response_id": response["id"],
        "provider_status": response["status"],
        "response_sha256": response_sha256,
        "usage": response["usage"],
        "budget": settled,
        "cost_basis": ("declared_price_ceiling_not_invoice" if cost_enabled
                       else "not_configured"),
        "criterion_4": "not_assessed",
    }


class OpenAIResponsesHTTP:
    """Minimal synchronous HTTP transport; no automatic application retry."""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request: urllib.request.Request, fp: Any,
                             code: int, msg: str, headers: Any,
                             newurl: str) -> None:
            return None

    def __init__(self, api_key: str, *, timeout_seconds: float = 90,
                 base_url: str = "https://api.openai.com/v1") -> None:
        if not api_key or timeout_seconds <= 0:
            raise DispatchError("API key and positive timeout are required")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._base_url = base_url.rstrip("/")
        self._opener = urllib.request.build_opener(self._NoRedirect())

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self._base_url + endpoint,
            data=_json_bytes(payload),
            headers={"Authorization": f"Bearer {self._api_key}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as stream:
                raw = stream.read(MAX_JSON_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise DispatchError(f"provider HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DispatchError("provider transport failed") from exc
        if len(raw) > MAX_JSON_BYTES:
            raise DispatchError("provider JSON exceeds the byte limit")
        try:
            value = json.loads(raw, object_pairs_hook=_unique_pairs,
                               parse_constant=_reject_constant)
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise DispatchError("provider JSON is invalid") from exc
        if type(value) is not dict:
            raise DispatchError("provider JSON is not an object")
        return value

    def count_input(self, payload: dict[str, Any]) -> int:
        value = self._post("/responses/input_tokens", payload)
        count = value.get("input_tokens")
        if value.get("object") != "response.input_tokens" or type(count) is not int:
            raise DispatchError("provider input count is invalid")
        return count

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/responses", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create one private shared run ledger")
    init.add_argument("ledger_dir", type=Path)
    init.add_argument("--limit-tokens", type=int, default=80_000)
    init.add_argument("--max-requests", type=int, required=True)
    init.add_argument("--cost-limit-micro-usd", type=int)
    init.add_argument("--price-profile", type=Path)
    send = sub.add_parser("send", help="send exactly one bounded Responses request")
    send.add_argument("ledger_dir", type=Path)
    send.add_argument("request_file", type=Path)
    send.add_argument("response_file", type=Path)
    send.add_argument("--request-id", required=True)
    send.add_argument("--role", required=True)
    send.add_argument("--allow-paid-request", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            profile = (_read_json_file(args.price_profile)
                       if args.price_profile is not None else None)
            ledger = TokenLedger.create(args.ledger_dir, args.limit_tokens,
                                        args.max_requests,
                                        cost_limit_micro_usd=args.cost_limit_micro_usd,
                                        price_profile=profile)
            result = {"classification": "development_token_ledger_unsealed",
                      "ledger": ledger.status(), "provider_calls": 0}
        else:
            if not args.allow_paid_request:
                raise DispatchError("send requires --allow-paid-request")
            ledger = TokenLedger(args.ledger_dir)
            if ledger.status()["cost_limit_micro_usd"] is None:
                raise DispatchError("paid send requires a prepared cost ceiling")
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise DispatchError("OPENAI_API_KEY is unavailable")
            request = _read_json_file(args.request_file)
            result = dispatch_response(
                ledger, request_id=args.request_id, role=args.role,
                request=request, response_path=args.response_file,
                transport=OpenAIResponsesHTTP(api_key),
            )
    except (BudgetError, DispatchError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
