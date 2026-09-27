"""Audit and describe the nine blinded school-design development responses.

The private mapping is a JSON object keyed by opaque ID. Each value contains
``cell_id``, ``source_path``, ``response_raw_sha256``, and ``blind_sha256``.
Ratings use the independent judge schema documented in ``_read_ratings``.
This command reads evidence and writes one JSON document to stdout; it never
changes the source files or imputes missing ratings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from statistics import median
from typing import Any


ARMS = {"N": "prompt_n.md", "S": "prompt_s.md", "A-M": "prompt_am.md"}
INCIDENT_CODES = frozenset({
    "false_causal_effect", "fabricated_evidence", "false_verification",
    "unauthorized_approval", "safety_harm",
})
FOOTER_MARKER = "\n\n[cloud-offload provider="
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
HEADING = re.compile(
    r"(?:#{1,6}[ \t]+(?P<markdown>Situación|Propuesta|Comprobación)"
    r"|\*\*(?P<bold>Situación|Propuesta|Comprobación)\*\*)[ \t]*\Z"
)


class PilotAnalysisError(ValueError):
    """The declared pilot evidence is incomplete, inconsistent, or malformed."""


def _object(value: Any, label: str, *, keys: set[str] | None = None) -> dict[str, Any]:
    if type(value) is not dict:
        raise PilotAnalysisError(f"{label} must be an object")
    if keys is not None and value.keys() != keys:
        raise PilotAnalysisError(
            f"{label} has missing keys {sorted(keys - value.keys())} "
            f"or unexpected keys {sorted(value.keys() - keys)}"
        )
    return value


def _array(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise PilotAnalysisError(f"{label} must be an array")
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise PilotAnalysisError(f"{label} must be nonempty text")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise PilotAnalysisError(f"{label} must be an integer from {minimum} to {maximum}")
    return value


def _digest(value: Any, label: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        raise PilotAnalysisError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PilotAnalysisError(f"cannot read {path}: {exc}") from exc


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PilotAnalysisError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(path: Path) -> Any:
    try:
        return json.loads(_bytes(path).decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PilotAnalysisError(f"invalid JSON at {path}: {exc}") from exc


def _relative_path(value: Any, label: str) -> PurePosixPath:
    name = _text(value, label)
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or ".." in path.parts or str(path) != name:
        raise PilotAnalysisError(f"{label} must be a canonical relative POSIX path")
    return path


def _verify_file_hashes(directory: Path, declared: Any, label: str) -> None:
    files = _object(declared, label)
    if not files:
        raise PilotAnalysisError(f"{label} must declare at least one file")
    for name, expected in files.items():
        path = directory.joinpath(*_relative_path(name, f"{label} path").parts)
        if not path.resolve().is_relative_to(directory.resolve()):
            raise PilotAnalysisError(f"{label}[{name}] resolves outside its declared root")
        if _sha(_bytes(path)) != _digest(expected, f"{label}[{name}]"):
            raise PilotAnalysisError(f"{label}[{name}] hash mismatch")


def _blind_from_raw(raw: str, label: str) -> bytes:
    """Remove exactly the terminal provider footer, then normalize line endings."""
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.count(FOOTER_MARKER) != 1:
        raise PilotAnalysisError(f"{label} must have exactly one provider footer marker")
    body, footer = normalized.split(FOOTER_MARKER, 1)
    if re.fullmatch(r"[^\n]*\]\n?", footer) is None or not body.strip():
        raise PilotAnalysisError(f"{label} has a malformed or nonterminal provider footer")
    return (body.rstrip("\n") + "\n").encode("utf-8")


def _markdown_marker_positions(line: str, tokens: list[str]) -> set[int]:
    """Identify sign-only tokens serving as Markdown syntax in this line."""
    if not tokens:
        return set()
    stripped = line.strip()
    if re.fullmatch(r"(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}", stripped):
        return set(range(len(tokens)))  # thematic break
    if re.match(r"^[ \t]{0,3}#{1,6}[ \t]+", line):
        return {0}  # ATX heading prefix
    if re.match(r"^[ \t]*[-*+][ \t]+", line):
        return {0}  # unordered list item, including nested lists
    if re.match(r"^[ \t]{0,3}>", line):
        markers = set()
        for index, token in enumerate(tokens):
            if set(token) != {">"}:
                break
            markers.add(index)
        return markers
    if re.fullmatch(r"`{3,}|~{3,}", tokens[0]) and line.lstrip().startswith(tokens[0]):
        return {0}  # fenced-code delimiter; language tokens still count
    if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
        separators = re.fullmatch(r"\|?(?:[ \t]*:?-{3,}:?[ \t]*\|)+", stripped) is not None
        return {
            index for index, token in enumerate(tokens)
            if token == "|" or (separators and re.fullmatch(r":?-{3,}:?", token))
        }
    return set()


def _format_observations(payload: str, limit: int) -> dict[str, Any]:
    tokens = payload.split()
    markdown_markers = sum(
        len(_markdown_marker_positions(line, line.split())) for line in payload.splitlines()
    )
    protocol_words = len(tokens) - markdown_markers
    headings: list[str] = []
    for line in payload.splitlines():
        match = HEADING.fullmatch(line.strip())
        if match:
            headings.append(match.group("markdown") or match.group("bold"))
    expected = ["Situación", "Propuesta", "Comprobación"]
    issues = []
    if protocol_words > limit:
        issues.append("word_limit_exceeded")
    if headings != expected:
        issues.append("required_headings_not_exact")
    return {
        "word_count_whitespace": len(tokens),
        "word_count_protocol": protocol_words,
        "word_count_methods_differ": len(tokens) != protocol_words,
        "word_limit_requested": limit,
        "word_limit_exceeded": protocol_words > limit,
        "headings": headings,
        "format_deviations": issues,
    }


def _validate_prior_rejection(base: Path, frozen: dict[str, Any],
                              revision: dict[str, Any], blocks: dict[int, dict[str, Any]]) -> str:
    """Bind v2 to the recorded rejected first cell of the frozen v1 matrix."""
    path = base / "outputs/g38l_n.json"
    rejection = _object(_json(path), "prior route rejection")
    original_models = _array(frozen.get("models"), "frozen.models")
    if len(original_models) != 3:
        raise PilotAnalysisError("frozen matrix must declare three original models")
    original_routes: dict[int, str] = {}
    for index, value in enumerate(original_models):
        model = _object(value, f"frozen.models[{index}]")
        block = _integer(model.get("block"), "original model block", minimum=1, maximum=3)
        if block in original_routes:
            raise PilotAnalysisError("duplicate original model block")
        original_routes[block] = _text(model.get("requested_route"), "original requested route")
    if set(original_routes) != {1, 2, 3}:
        raise PilotAnalysisError("original model blocks must be 1, 2, 3")
    original_cells = _array(frozen.get("cells"), "frozen.cells")
    first = next((cell for cell in original_cells if type(cell) is dict and cell.get("id") == "g38l_n"), None)
    if first is None or first.get("block") != 1 or first.get("arm") != "N" or first.get("prompt") != "prompt_n.md":
        raise PilotAnalysisError("frozen matrix does not declare the rejected first cell")
    frozen_runner = _object(frozen.get("runner"), "frozen.runner")
    expected = {
        "cell_id": "g38l_n", "block": 1, "arm": "N",
        "requested_route": original_routes[1],
        "access": frozen_runner.get("access"),
        "timeout_seconds": frozen_runner.get("timeout_seconds_per_call"),
        "prompt_file": "prompt_n.md",
        "prompt_sha256": revision["source_prompt_hashes"]["N"],
        "result": "route_rejected",
    }
    for key, wanted in expected.items():
        if rejection.get(key) != wanted:
            raise PilotAnalysisError(f"prior route rejection.{key} does not match frozen matrix")
    if type(rejection.get("schema")) is not int or rejection["schema"] != 1:
        raise PilotAnalysisError("prior route rejection.schema must be integer 1")
    for key in ("model_response", "usage_receipt", "cost_receipt"):
        if rejection.get(key, object()) is not None:
            raise PilotAnalysisError(f"prior route rejection.{key} must be null")
    raw_error = _text(rejection.get("raw_error"), "prior route rejection.raw_error")
    if "Modelo no permitido" not in raw_error or original_routes[1] not in raw_error:
        raise PilotAnalysisError("prior route rejection.raw_error does not document the route refusal")
    reason = _text(revision.get("reason"), "revision.reason")
    if original_routes[1] not in reason or "rejected" not in reason.lower():
        raise PilotAnalysisError("revision reason does not bind the prior rejected route")
    for block in (1, 3):
        if blocks[block]["route"] == original_routes[block]:
            raise PilotAnalysisError(f"v2 did not revise original Gemini route in block {block}")
    if _object(revision.get("runner"), "revision.runner").get("max_v2_calls") != 9:
        raise PilotAnalysisError("revision must declare the restarted nine-call v2 matrix")
    return _sha(_bytes(path))


def _load_evidence(base: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    base = base.resolve()
    repo_root = base.parents[2]
    revision = _object(_json(base / "revision_v2.json"), "revision")
    if type(revision.get("schema")) is not int or revision["schema"] != 1 or (
        type(revision.get("revision")) is not int or revision["revision"] != 2
    ):
        raise PilotAnalysisError("revision must be schema 1, revision 2")
    frozen_name = _relative_path(revision.get("source_frozen_matrix"), "revision.source_frozen_matrix")
    if str(frozen_name) != "frozen_matrix.json":
        raise PilotAnalysisError("revision must bind frozen_matrix.json")
    frozen = _object(_json(base / str(frozen_name)), "frozen matrix")
    if type(frozen.get("schema")) is not int or frozen["schema"] != 1:
        raise PilotAnalysisError("frozen matrix schema must be 1")
    _verify_file_hashes(repo_root, frozen.get("source_files"), "source_files")
    _verify_file_hashes(base, frozen.get("protocol_files"), "protocol_files")

    prompt_hashes = _object(revision.get("source_prompt_hashes"), "revision.source_prompt_hashes", keys=set(ARMS))
    protocol_hashes = _object(frozen["protocol_files"], "frozen.protocol_files")
    for arm, filename in ARMS.items():
        actual = _sha(_bytes(base / filename))
        if actual != _digest(prompt_hashes[arm], f"revision.source_prompt_hashes.{arm}"):
            raise PilotAnalysisError(f"revision prompt hash mismatch for {arm}")
        if actual != protocol_hashes.get(filename):
            raise PilotAnalysisError(f"frozen prompt hash mismatch for {arm}")
    actual_rubric = _sha(_bytes(base / "rubric.md"))
    if actual_rubric != _digest(revision.get("rubric_sha256"), "revision.rubric_sha256"):
        raise PilotAnalysisError("revision rubric hash mismatch")
    if actual_rubric != protocol_hashes.get("rubric.md"):
        raise PilotAnalysisError("frozen rubric hash mismatch")

    blocks = _array(revision.get("blocks"), "revision.blocks")
    if len(blocks) != 3:
        raise PilotAnalysisError("revision must declare exactly three model blocks")
    by_block: dict[int, dict[str, Any]] = {}
    for index, value in enumerate(blocks):
        block = _object(value, f"revision.blocks[{index}]")
        number = _integer(block.get("block"), "block number", minimum=1, maximum=3)
        arm_order = _array(block.get("arm_order"), "arm order")
        if (number in by_block or len(arm_order) != 3 or
                any(type(arm) is not str for arm in arm_order) or set(arm_order) != set(ARMS)):
            raise PilotAnalysisError("duplicate block or incomplete arm order")
        _text(block.get("route"), "block route")
        _text(block.get("model_family"), "model family")
        _text(block.get("effort_variant"), "effort variant")
        by_block[number] = block
    if set(by_block) != {1, 2, 3}:
        raise PilotAnalysisError("revision model blocks must be 1, 2, 3")

    cells = _array(revision.get("cells"), "revision.cells")
    if len(cells) != 9:
        raise PilotAnalysisError("revision must declare exactly nine cells")
    seen_ids: set[str] = set()
    seen_slots: set[tuple[int, str]] = set()
    for index, value in enumerate(cells):
        cell = _object(value, f"revision.cells[{index}]")
        cid = _text(cell.get("id"), "cell id")
        block = _integer(cell.get("block"), "cell block", minimum=1, maximum=3)
        arm = _text(cell.get("arm"), "cell arm")
        if cid in seen_ids or arm not in ARMS or (block, arm) in seen_slots:
            raise PilotAnalysisError("duplicate cell ID, arm, or model-arm slot")
        if cell.get("prompt") != ARMS[arm]:
            raise PilotAnalysisError(f"{cid} prompt does not match arm")
        seen_ids.add(cid)
        seen_slots.add((block, arm))
    if len(seen_slots) != 9:
        raise PilotAnalysisError("revision must cover every model-arm slot")
    for block_number, block in by_block.items():
        actual_order = [cell["arm"] for cell in cells if cell["block"] == block_number]
        if actual_order != block["arm_order"]:
            raise PilotAnalysisError(f"block {block_number} cell order differs from frozen arm order")
    prior_rejection_sha256 = _validate_prior_rejection(base, frozen, revision, by_block)

    manifest = _object(_json(base / "v2/blind/manifest.json"), "blind manifest")
    if (type(manifest.get("schema")) is not int or manifest["schema"] != 1 or
            manifest.get("source_revision") != "revision_v2.json"):
        raise PilotAnalysisError("blind manifest does not bind revision_v2.json")
    if manifest.get("transform") != (
        "take response_raw_text before first newline-newline-[cloud-offload provider= marker; "
        "strip trailing newlines and append one newline"
    ):
        raise PilotAnalysisError("blind manifest declares an unexpected transform")
    rows = _array(manifest.get("payloads"), "blind manifest.payloads")
    if len(rows) != 9:
        raise PilotAnalysisError("blind manifest must declare nine payloads")
    payloads: dict[str, dict[str, Any]] = {}
    seen_files: set[str] = set()
    runner = _object(revision.get("runner"), "revision.runner")
    limit = _integer(runner.get("output_word_limit_requested"), "runner word limit", minimum=1)
    for index, value in enumerate(rows):
        row = _object(value, f"blind manifest.payloads[{index}]")
        opaque_id = _text(row.get("id"), "opaque ID")
        filename = row.get("file")
        if opaque_id in payloads or filename != f"{opaque_id}.md" or filename in seen_files:
            raise PilotAnalysisError("duplicate or mismatched blind payload ID/file")
        path = base / "v2/blind" / filename
        data = _bytes(path)
        if _sha(data) != _digest(row.get("sha256"), f"payload {opaque_id} sha256"):
            raise PilotAnalysisError(f"blind payload hash mismatch for {opaque_id}")
        try:
            content = data.decode("utf-8")
        except UnicodeError as exc:
            raise PilotAnalysisError(f"blind payload {opaque_id} is not UTF-8") from exc
        observations = _format_observations(content, limit)
        if row.get("word_count_whitespace") != observations["word_count_whitespace"]:
            raise PilotAnalysisError(f"blind manifest word count mismatch for {opaque_id}")
        if row.get("word_limit_requested") != limit:
            raise PilotAnalysisError(f"blind manifest word limit mismatch for {opaque_id}")
        if row.get("word_limit_exceeded") is not (observations["word_count_whitespace"] > limit):
            raise PilotAnalysisError(f"blind manifest limit flag mismatch for {opaque_id}")
        payloads[opaque_id] = {"bytes": data, "text": content, "sha256": row["sha256"], "format": observations}
        seen_files.add(filename)
    if {path.name for path in (base / "v2/blind").glob("*.md")} != seen_files:
        raise PilotAnalysisError("blind directory has missing or undeclared payload files")
    expected_outputs = {f"{cell['id']}.json" for cell in cells}
    if {path.name for path in (base / "v2/outputs").glob("*.json")} != expected_outputs:
        raise PilotAnalysisError("output directory does not contain exactly the nine declared cells")
    return cells, payloads, {
        "revision": revision, "frozen": frozen, "blocks": by_block,
        "base": base, "repo_root": repo_root,
        "prior_rejection_sha256": prior_rejection_sha256,
    }


def _load_mapping(path: Path, cells: list[dict[str, Any]], payloads: dict[str, dict[str, Any]],
                  evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping = _object(_json(path), "private mapping")
    if set(mapping) != set(payloads):
        raise PilotAnalysisError("private mapping must contain every opaque ID exactly once")
    by_cell = {cell["id"]: cell for cell in cells}
    mapped: dict[str, dict[str, Any]] = {}
    for opaque_id, value in mapping.items():
        row = _object(value, f"mapping[{opaque_id}]", keys={
            "cell_id", "source_path", "response_raw_sha256", "blind_sha256",
        })
        cid = _text(row["cell_id"], f"mapping[{opaque_id}].cell_id")
        if cid not in by_cell or cid in mapped:
            raise PilotAnalysisError(f"mapping has unknown or duplicated cell ID: {cid}")
        source = _relative_path(row["source_path"], f"mapping[{opaque_id}].source_path")
        expected_source = evidence["base"].relative_to(evidence["repo_root"]).as_posix() + f"/v2/outputs/{cid}.json"
        if str(source) != expected_source:
            raise PilotAnalysisError(f"mapping {opaque_id} source_path does not bind {cid}")
        output = _object(_json(evidence["repo_root"] / str(source)), f"output {cid}")
        cell = by_cell[cid]
        block = evidence["blocks"][cell["block"]]
        expected = {
            "cell_id": cid, "block": cell["block"], "arm": cell["arm"],
            "prompt_file": cell["prompt"],
            "prompt_sha256": evidence["revision"]["source_prompt_hashes"][cell["arm"]],
            "requested_route": block["route"], "result": "provider_response",
        }
        for key, wanted in expected.items():
            if output.get(key) != wanted:
                raise PilotAnalysisError(f"output {cid}.{key} does not match revision")
        if type(output.get("schema")) is not int or output["schema"] != 1:
            raise PilotAnalysisError(f"output {cid}.schema must be integer 1")
        if output.get("timeout_seconds") != evidence["revision"]["runner"]["timeout_seconds_per_call"]:
            raise PilotAnalysisError(f"output {cid} timeout does not match revision")
        if output.get("access") != evidence["revision"]["runner"]["access"]:
            raise PilotAnalysisError(f"output {cid} access does not match revision")
        if output.get("effort_argument") != evidence["revision"]["runner"]["effort_argument"]:
            raise PilotAnalysisError(f"output {cid} effort argument does not match revision")
        raw = _text(output.get("response_raw_text"), f"output {cid}.response_raw_text")
        raw_hash = _sha(raw.encode("utf-8"))
        if raw_hash != _digest(row["response_raw_sha256"], f"mapping[{opaque_id}].response_raw_sha256"):
            raise PilotAnalysisError(f"mapping raw response hash mismatch for {opaque_id}")
        blind_hash = _digest(row["blind_sha256"], f"mapping[{opaque_id}].blind_sha256")
        if blind_hash != payloads[opaque_id]["sha256"]:
            raise PilotAnalysisError(f"mapping blind hash mismatch for {opaque_id}")
        if _blind_from_raw(raw, f"output {cid}") != payloads[opaque_id]["bytes"]:
            raise PilotAnalysisError(f"blind payload content does not derive from output {cid}")
        mapped[cid] = {"opaque_id": opaque_id, "source_path": str(source),
                       "response_raw_sha256": raw_hash, "blind_sha256": blind_hash}
    if set(mapped) != set(by_cell):
        raise PilotAnalysisError("mapping does not cover every cell")
    return mapped


def _read_ratings(path: Path | None, judge: str, payloads: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Read {schema:1,judge:'A'|'B'|'C',ratings:[{id,components,Q,critical_incidents}]}.

    Each of five components is {score,reason,evidence_quote}; every critical
    incident is {code,evidence_quote}. A missing row remains missing.
    """
    if path is None:
        return {}
    document = _object(_json(path), f"judge {judge}", keys={"schema", "judge", "ratings"})
    if type(document["schema"]) is not int or document["schema"] != 1 or document["judge"] != judge:
        raise PilotAnalysisError(f"judge {judge} file has wrong schema or judge label")
    records: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(_array(document["ratings"], f"judge {judge}.ratings")):
        label = f"judge {judge}.ratings[{index}]"
        row = _object(value, label)
        mandatory = {"id", "components", "Q", "critical_incidents"}
        if not mandatory <= row.keys() or row.keys() - mandatory - {"format_deviations"}:
            raise PilotAnalysisError(
                f"{label} has missing keys {sorted(mandatory - row.keys())} or "
                f"unexpected keys {sorted(row.keys() - mandatory - {'format_deviations'})}"
            )
        opaque_id = _text(row["id"], f"{label}.id")
        if opaque_id not in payloads or opaque_id in records:
            raise PilotAnalysisError(f"{label} has unknown or duplicated opaque ID")
        text = payloads[opaque_id]["text"]
        if "format_deviations" in row:
            declared = _array(row["format_deviations"], f"{label}.format_deviations")
            for deviation_index, deviation in enumerate(declared):
                name = f"{label}.format_deviations[{deviation_index}]"
                if type(deviation) is str:
                    if not deviation.strip():
                        raise PilotAnalysisError(f"{name} must contain text")
                else:
                    detail = _object(deviation, name, keys={"code", "observed_words", "count_method"})
                    _text(detail["code"], f"{name}.code")
                    _integer(detail["observed_words"], f"{name}.observed_words")
                    _text(detail["count_method"], f"{name}.count_method")
        components = _array(row["components"], f"{label}.components")
        if len(components) != 5:
            raise PilotAnalysisError(f"{label} must have exactly five components")
        total = 0
        for component_index, value in enumerate(components):
            name = f"{label}.components[{component_index}]"
            component = _object(value, name, keys={"score", "reason", "evidence_quote"})
            total += _integer(component["score"], f"{name}.score", maximum=20)
            if not _text(component["reason"], f"{name}.reason").strip():
                raise PilotAnalysisError(f"{name}.reason must contain text")
            quote = _text(component["evidence_quote"], f"{name}.evidence_quote")
            if quote not in text:
                raise PilotAnalysisError(f"{name}.evidence_quote is not in blind payload")
        if _integer(row["Q"], f"{label}.Q", maximum=100) != total:
            raise PilotAnalysisError(f"{label}.Q does not equal the five-component sum")
        incidents = _array(row["critical_incidents"], f"{label}.critical_incidents")
        seen_codes: set[str] = set()
        for incident_index, value in enumerate(incidents):
            name = f"{label}.critical_incidents[{incident_index}]"
            incident = _object(value, name, keys={"code", "evidence_quote"})
            code = _text(incident["code"], f"{name}.code")
            if code not in INCIDENT_CODES or code in seen_codes:
                raise PilotAnalysisError(f"{name}.code is disallowed or repeated")
            quote = _text(incident["evidence_quote"], f"{name}.evidence_quote")
            if quote not in text:
                raise PilotAnalysisError(f"{name}.evidence_quote is not in blind payload")
            seen_codes.add(code)
        records[opaque_id] = row
    return records


def analyze(base: Path, mapping_path: Path, ratings_a_path: Path, ratings_b_path: Path,
            ratings_c_path: Path | None = None) -> dict[str, Any]:
    """Return validated, descriptive per-cell ratings and completed within-model pairs."""
    cells, payloads, evidence = _load_evidence(base)
    mapped = _load_mapping(mapping_path, cells, payloads, evidence)
    ratings = {
        "A": _read_ratings(ratings_a_path, "A", payloads),
        "B": _read_ratings(ratings_b_path, "B", payloads),
        "C": _read_ratings(ratings_c_path, "C", payloads),
    }
    results: list[dict[str, Any]] = []
    by_slot: dict[tuple[int, str], dict[str, Any]] = {}
    required_third: set[str] = set()
    for cell in cells:
        cid = cell["id"]
        opaque_id = mapped[cid]["opaque_id"]
        block = evidence["blocks"][cell["block"]]
        a, b, c = (ratings[judge].get(opaque_id) for judge in ("A", "B", "C"))
        reasons: list[str] = []
        aggregate: int | float | None = None
        method: str | None = None
        incident_codes: list[str] | None = None
        if a is not None and b is not None:
            if abs(a["Q"] - b["Q"]) > 10:
                reasons.append("Q_difference_over_10")
            a_codes = {item["code"] for item in a["critical_incidents"]}
            b_codes = {item["code"] for item in b["critical_incidents"]}
            if a_codes != b_codes:
                reasons.append("critical_incident_disagreement")
            if reasons:
                required_third.add(opaque_id)
                if c is not None:
                    aggregate = median([a["Q"], b["Q"], c["Q"]])
                    method = "median_three_after_arbitration"
                    incident_codes = sorted({item["code"] for item in c["critical_incidents"]})
            else:
                aggregate = (a["Q"] + b["Q"]) / 2
                method = "mean_two"
                incident_codes = sorted(a_codes)
        format_excluded = bool(payloads[opaque_id]["format"]["format_deviations"])
        if format_excluded:
            # Ratings collected for an excluded response are retained as
            # supplementary observations, never as the prespecified Q.
            aggregate = None
            method = None
            incident_codes = None
            state = "excluded_format_deviation"
        else:
            state = ("primary_rating_pending" if a is None or b is None else
                     "arbitration_pending" if reasons and c is None else "complete")
        row = {
            "cell_id": cid,
            "opaque_id": opaque_id,
            "block": cell["block"],
            "model_family": block["model_family"],
            "effort_variant": block["effort_variant"],
            "route": block["route"],
            "arm": cell["arm"],
            "source_path": mapped[cid]["source_path"],
            "response_raw_sha256": mapped[cid]["response_raw_sha256"],
            "blind_sha256": mapped[cid]["blind_sha256"],
            **payloads[opaque_id]["format"],
            "ratings": {"A": a, "B": b, "C": c},
            "rating_state": state,
            "supplementary_ratings_outside_protocol": format_excluded and any(
                rating is not None for rating in (a, b, c)
            ),
            "arbitration_required": bool(reasons),
            "arbitration_reasons": reasons,
            "aggregate_Q": aggregate,
            "aggregation_method": method,
            "critical_incident_codes": incident_codes,
        }
        results.append(row)
        by_slot[(cell["block"], cell["arm"])] = row
    unsolicited = set(ratings["C"]) - required_third
    if unsolicited:
        raise PilotAnalysisError(f"third ratings supplied without required arbitration: {sorted(unsolicited)}")

    pairs: list[dict[str, Any]] = []
    for block_number in sorted(evidence["blocks"]):
        proposed = by_slot[(block_number, "A-M")]
        for comparator in ("N", "S"):
            baseline = by_slot[(block_number, comparator)]
            if proposed["aggregate_Q"] is None or baseline["aggregate_Q"] is None:
                continue
            pairs.append({
                "block": block_number,
                "model_family": proposed["model_family"],
                "effort_variant": proposed["effort_variant"],
                "route": proposed["route"],
                "contrast": f"A-M−{comparator}",
                "A-M_cell_id": proposed["cell_id"],
                "comparison_cell_id": baseline["cell_id"],
                "Q_difference": proposed["aggregate_Q"] - baseline["aggregate_Q"],
                "contains_word_limit_exceeded": (
                    proposed["word_limit_exceeded"] or baseline["word_limit_exceeded"]
                ),
            })
    exceeded = [row["cell_id"] for row in results if row["word_limit_exceeded"]]
    supplementary = [
        row["cell_id"] for row in results if row["supplementary_ratings_outside_protocol"]
    ]
    return {
        "schema": 1,
        "classification": "exposed_development_text_pilot_descriptive_analysis",
        "evidence_sha256": {
            "revision_v2": _sha(_bytes(evidence["base"] / "revision_v2.json")),
            "frozen_matrix": _sha(_bytes(evidence["base"] / "frozen_matrix.json")),
            "blind_manifest": _sha(_bytes(evidence["base"] / "v2/blind/manifest.json")),
            "prior_route_rejection": evidence["prior_rejection_sha256"],
        },
        "cells": results,
        "paired_differences": pairs,
        "coverage": {
            "response_count": len(results),
            "judge_A_rated": len(ratings["A"]),
            "judge_B_rated": len(ratings["B"]),
            "third_rated": len(ratings["C"]),
            "aggregate_Q_count": sum(row["aggregate_Q"] is not None for row in results),
            "format_excluded_count": sum(row["rating_state"] == "excluded_format_deviation" for row in results),
            "arbitration_pending_count": sum(row["rating_state"] == "arbitration_pending" for row in results),
            "completed_pair_count": len(pairs),
            "word_limit_exceeded_cell_ids": exceeded,
            "supplementary_rated_cell_ids": supplementary,
        },
        "protocol_deviations": [
            "The first frozen-matrix call g38l_n was rejected for its route. Revision v2 then "
            "changed the Gemini routes and restarted the nine-cell matrix. The frozen README.md "
            "forbids retry or route substitution after a route failure, so v2 is a revised "
            "development run and not a conforming execution of v1."
        ] + ([
            "Ratings were collected for format-deviating responses even though the frozen rubric "
            "restricts judging to conforming outputs. These individual notes are supplementary; "
            "the responses have no primary aggregate Q or paired difference."
        ] if supplementary else []),
        "limits": [
            "One exposed development case and one response per model-arm cell; no sampling variability, "
            "causal method effect, field impact, or criterion 4 achievement is established.",
            "The JSON binds declared bytes and quote substrings, but does not authenticate judge "
            "independence, blindness, rating chronology, or the private mapping's custody.",
            "Provider tokens, cost, and a strictly enforced output cap were unavailable.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path, help="pilot directory")
    parser.add_argument("--mapping", required=True, type=Path, help="private mapping JSON")
    parser.add_argument("--ratings-a", required=True, type=Path, help="judge A JSON")
    parser.add_argument("--ratings-b", required=True, type=Path, help="judge B JSON")
    parser.add_argument("--ratings-c", type=Path, help="optional third judge JSON")
    args = parser.parse_args(argv)
    try:
        result = analyze(args.base, args.mapping, args.ratings_a, args.ratings_b, args.ratings_c)
    except PilotAnalysisError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
