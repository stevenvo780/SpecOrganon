"""Development-only Responses dispatcher with a pre-send, shared token reservation.

This path sends one request at a time. It does not execute tools, manage an
agent conversation, enforce time/cost limits, or make a CLI opaque to the
caller safe for a confirmatory study. The caller must use one ledger directory
for every request and agent in the same run. Provider calls require an explicit
CLI flag and an API key; tests inject a local fake transport.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from managed_token_ledger import BudgetError, TokenLedger


MAX_JSON_BYTES = 16 * 1024 * 1024
REQUEST_KEYS = frozenset({"model", "input", "instructions", "reasoning", "max_output_tokens"})


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


def _validated_request(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict or not {"model", "input", "max_output_tokens"} <= raw.keys() \
            or not raw.keys() <= REQUEST_KEYS:
        raise DispatchError("request has missing or unsupported fields")
    if type(raw["model"]) is not str or not raw["model"].strip():
        raise DispatchError("model must be a nonempty string")
    if type(raw["input"]) not in (str, list) or not raw["input"]:
        raise DispatchError("input must be nonempty text or a message array")
    if type(raw["input"]) is list:
        if any(type(item) is not dict or set(item) != {"role", "content"}
               or item["role"] not in {"system", "developer", "user", "assistant"}
               or type(item["content"]) is not str or not item["content"]
               for item in raw["input"]):
            raise DispatchError("message array must contain only text roles and content")
    if "instructions" in raw and (type(raw["instructions"]) is not str
                                  or not raw["instructions"]):
        raise DispatchError("instructions must be nonempty text")
    if "reasoning" in raw:
        reasoning = raw["reasoning"]
        if (type(reasoning) is not dict or set(reasoning) != {"effort"}
                or reasoning["effort"] not in
                {"none", "low", "medium", "high", "xhigh", "max"}):
            raise DispatchError("reasoning must specify a supported effort")
    if type(raw["max_output_tokens"]) is not int or raw["max_output_tokens"] < 1:
        raise DispatchError("max_output_tokens must be a positive integer")
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
    count_payload = {key: value for key, value in payload.items()
                     if key != "max_output_tokens"}
    count_bytes = _json_bytes(count_payload)
    input_tokens = transport.count_input(count_payload)
    if type(input_tokens) is not int or input_tokens < 1:
        raise DispatchError("provider input count is missing or invalid")
    if _json_bytes(count_payload) != count_bytes:
        raise DispatchError("input changed during token counting")
    digest = hashlib.sha256(_json_bytes(payload)).hexdigest()
    ledger.reserve(request_id, role, digest, input_tokens,
                   payload["max_output_tokens"])
    try:
        provider_payload = {**payload, "store": False, "stream": False}
        response = transport.send(provider_payload)
        if type(response) is not dict:
            raise DispatchError("provider response is not an object")
        response_sha256 = _write_response(response_path, response)
        if (type(response.get("id")) is not str or not response["id"]
                or response.get("model") != payload["model"]
                or response.get("status") not in {"completed", "incomplete"}):
            raise DispatchError("provider identity or status is not verifiable")
        usage = response.get("usage")
        measured = ({key: usage.get(key) for key in
                     ("input_tokens", "output_tokens", "total_tokens")}
                    if type(usage) is dict else usage)
        settled = ledger.settle(request_id, measured)
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
            value = json.loads(raw)
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
            ledger = TokenLedger.create(args.ledger_dir, args.limit_tokens,
                                        args.max_requests)
            result = {"classification": "development_token_ledger_unsealed",
                      "ledger": ledger.status(), "provider_calls": 0}
        else:
            if not args.allow_paid_request:
                raise DispatchError("send requires --allow-paid-request")
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise DispatchError("OPENAI_API_KEY is unavailable")
            raw = args.request_file.read_bytes()
            if len(raw) > MAX_JSON_BYTES:
                raise DispatchError("request exceeds the byte limit")
            request = json.loads(raw)
            ledger = TokenLedger(args.ledger_dir)
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
