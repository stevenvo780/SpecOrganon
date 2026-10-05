"""Controls for reserved evaluator, not solutions to the study's software tasks."""
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "experiments/software_comparison_v1/reserved/evaluator.py"
SPEC = importlib.util.spec_from_file_location("reserved_evaluator", PATH)
E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E)


def measured(stdout=b"", stderr=b"", code=0, **extra):
    return {"stdout": stdout, "stderr": stderr, "exit_code": code,
            "timed_out": False, "truncated_streams": [], **extra}


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":{"y":1,"y":2}}',
                                 b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e9999}',
                                 b'{}{}', b'\xff', b'\xef\xbb\xbf{}'])
def test_exact_output_rejects_ambiguous_json(raw):
    with pytest.raises((ValueError, UnicodeError)):
        E.exact_json(raw)


@pytest.mark.parametrize("actual,expected", [(True, 1), (1.0, 1), ([True], [1]),
                                             ({"cost": True}, {"cost": 1}),
                                             ({"x": 1, "extra": 2}, {"x": 1})])
def test_typed_equality_rejects_python_numeric_coercion(actual, expected):
    assert not E.same_typed(actual, expected)


def test_framing_and_types_are_not_promoted_by_exit_zero():
    case = {"expected": {"reachable": True, "cost": 1, "path": ["A", "B"]}}
    good = b'{"path":["A","B"],"cost":1,"reachable":true}\n'
    assert E.judge(case, measured(good))["status"] == "pass"
    for bad in [good[:-1], good.replace(b'"cost":1', b'"cost":true'),
                good + b'{}\n', good.replace(b'"cost":1', b'"cost":1.0')]:
        assert E.judge(case, measured(bad))["status"] == "fail"
    assert E.judge(case, measured(good, b"debug\n"))["status"] == "fail"
    assert E.judge(case, measured(good, code=1))["status"] == "fail"


def test_errors_and_limits_have_exact_outcomes():
    case = {"expected": None}
    assert E.judge(case, measured(stderr=b'{"error":"invalid_input"}\n', code=2))["status"] == "pass"
    assert E.judge(case, measured(stderr=b'Traceback\n', code=2))["status"] == "fail"
    assert E.judge(case, measured(stderr=b'{"error":"invalid_input"}\n', code=0))["status"] == "fail"
    assert E.judge(case, measured(timed_out=True))["status"] == "fail"
    assert E.judge(case, measured(truncated_streams=["stdout"]))["status"] == "fail"
    assert E.judge(case, measured(infrastructure_error="handle missing"))["status"] == "inconclusive"


def test_simple_path_oracle_manual_cases_and_permutations():
    nodes = ["S", "A", "B", "C", "End"]
    edges = [{"source": a, "target": b, "cost": c} for a, b, c in
             [("S", "End", 3), ("S", "B", 1), ("B", "End", 2),
              ("S", "A", 1), ("A", "C", 1), ("C", "End", 1), ("A", "S", 1)]]
    expect = {"reachable": True, "cost": 3, "path": ["S", "A", "C", "End"]}
    assert E.path_oracle(nodes, edges, "S", "End") == expect
    assert E.path_oracle(nodes[::-1], edges[::-1], "S", "End") == expect
    assert E.path_oracle(nodes, edges, "S", "S") == {"reachable": True, "cost": 0, "path": ["S"]}
    assert E.path_oracle(nodes, edges, "End", "S") == {"reachable": False, "cost": None, "path": []}


def test_reserved_suite_is_deterministic_and_not_a_release_or_delivery():
    a, b = E.suite(), E.suite()
    assert E.encoded(a) == E.encoded(b)
    assert a["status"] == "draft_not_preregistered"
    assert {c["task"] for c in a["cases"]} == {"routeplan", "treemap"}
    route = {c["id"]: c for c in a["cases"] if c["task"] == "routeplan"}
    assert len(bytes.fromhex(route["byte-cap"]["stdin_hex"])) == 65536
    assert len(bytes.fromhex(route["byte-over-cap"]["stdin_hex"])) == 65537
    assert len(json.loads(bytes.fromhex(route["edge-cap"]["stdin_hex"]))["edges"]) == 128
    assert route["full-list-tie"]["expected"]["path"] == ["S", "a", "c", "z"]
    for case in a["cases"]:
        raw = E.encoded(case["expected"] if case["expected"] is not None else {"error": "invalid_input"}) + b"\n"
        output = measured(raw) if case["expected"] is not None else measured(stderr=raw, code=2)
        assert E.judge(case, output)["status"] == "pass"


def test_declarative_tree_limits_include_filtered_and_nonregular_entries():
    entries = [{"kind": "file", "path": f"f{i}", "size": i} for i in range(256)]
    assert len(E.tree_expected(entries)["files"]) == 256
    assert E.tree_expected(entries, suffix=".txt") == {"files": [], "total_bytes": 0, "symlinks": []}
    assert E.tree_expected(entries + [{"kind": "fifo", "path": "pipe"}], suffix=".txt") is None
    tree = {c["id"]: c for c in E.tree_suite()}
    assert tree["path-bytes-512"]["expected"] is not None
    assert tree["path-bytes-513"]["expected"] is None
    assert tree["denied-at-depth-boundary"]["expected"] == {"files": [], "total_bytes": 0, "symlinks": []}
    assert tree["unreadable-directory"]["expected"] is None
    assert tree["depth-8-chain"]["expected"]["total_bytes"] == sum(range(1, 8))


def test_fixture_materialization_includes_sparse_links_fifo_and_byte_names(tmp_path):
    import os
    import stat
    entries = [{"kind": "dir", "path": "sub"},
               {"kind": "file", "path": "sub/sparse", "size": 8_000_003},
               {"kind": "file", "path_bytes_hex": "626164ff", "size": 1},
               {"kind": "link", "path": "shortcut", "target": "sub"},
               {"kind": "fifo", "path": "pipe"}]
    root = tmp_path / "root"
    E.materialize(root, entries)
    assert (root / "sub/sparse").stat().st_size == 8_000_003
    assert stat.S_ISLNK((root / "shortcut").lstat().st_mode)
    assert stat.S_ISFIFO((root / "pipe").lstat().st_mode)
    assert os.stat(os.fsencode(root) + b"/bad\xff").st_size == 1
    with pytest.raises(FileExistsError):
        E.materialize(root, [])


def test_relative_link_probe_uses_observed_cwd_and_dirfd():
    from experiments.software_comparison_v1.reserved.docker_evaluator import link_target_observations
    absolute = 'readlink("/fixture/root/link", "probe.txt", 4096) = 9'
    relative = 'chdir("/fixture/root") = 0\nreadlink("link", "probe.txt", 4096) = 9'
    directory_fd = 'readlinkat(3</fixture/root>, "link", "probe.txt", 4096) = 9'
    inherited = 'chdir("/fixture/root") = 0\nclone(child_stack=NULL, flags=SIGCHLD) = 33\n[pid 33] readlink("link", "probe.txt", 4096) = 9'
    for raw in [absolute, relative, directory_fd, inherited]:
        bad, unknown = link_target_observations(raw)
        assert len(bad) == 1 and not unknown
    bad, unknown = link_target_observations('fchdir(3) = 0\nreadlink("link", "probe.txt", 4096) = 9')
    assert not bad and len(unknown) == 1
    assert link_target_observations('readlink("/usr/bin/python3", "python3.12", 4096) = 10') == ([], [])
    shared = 'clone(flags=CLONE_FS|CLONE_THREAD) = 33\nchdir("/fixture/root") = 0\nreadlink("link", "probe.txt", 4096) = 9'
    bad, unknown = link_target_observations(shared)
    assert not bad and len(unknown) == 1


def test_capacity_fixtures_do_not_hide_limit_defects_behind_unknown_nodes_or_duplicate_edges():
    cases = {c['id']: c for c in E.route_suite()}
    too_many = json.loads(bytes.fromhex(cases['node-over-cap']['stdin_hex']))
    assert len(too_many['nodes']) == 33 and len(set(too_many['nodes'])) == 33
    assert all(e['source'] in too_many['nodes'] and e['target'] in too_many['nodes'] for e in too_many['edges'])
    assert set(too_many['query'].values()).issubset(too_many['nodes'])
    edges = json.loads(bytes.fromhex(cases['edge-over-cap']['stdin_hex']))
    assert len(edges['edges']) == 129
    assert len({(e['source'], e['target']) for e in edges['edges']}) == 129
    assert all(e['source'] in edges['nodes'] and e['target'] in edges['nodes'] for e in edges['edges'])
    assert len(edges['nodes']) <= 32


def test_utf8_path_byte_and_nonregular_entry_caps_have_separate_fixtures():
    cases = {c['id']: c for c in E.tree_suite()}
    assert cases['unicode-path-bytes-512']['expected'] is not None
    assert cases['unicode-path-bytes-513']['expected'] is None
    last = cases['unicode-path-bytes-513']['entries'][-1]['path']
    assert len(last) < 512 and len(last.encode('utf-8')) == 513
    mixed = cases['entry-over-cap-nonregular']
    assert len(mixed['entries']) == 257
    assert sum(e['kind'] == 'file' for e in mixed['entries']) == 1
    assert mixed['expected'] is None


def test_audit_cannot_accept_missing_or_incomplete_tracer_evidence():
    from experiments.software_comparison_v1.reserved.docker_evaluator import content_audit, audit_case
    case = audit_case()
    good_stdout = E.encoded(case['expected']) + b'\n'
    for trace in [b'', b'execve("/opt/specorganon/venv/bin/python", [], []) = 0\n']:
        assert content_audit(case, measured(good_stdout, trace=trace))['status'] == 'inconclusive'
    trace = b'execve("/opt/specorganon/venv/bin/python", [], []) = 0\nexit_group(0) = ?\n'
    assert content_audit(case, measured(good_stdout, stderr=trace))['status'] == 'inconclusive'
    assert content_audit(case, measured(good_stdout, trace=trace))['status'] == 'pass'
    forbidden = trace + b'openat(AT_FDCWD, "probe.txt", O_RDONLY) = 3</fixture/root/probe.txt>\n'
    assert content_audit(case, measured(good_stdout, trace=forbidden))['status'] == 'fail'
    safe = trace + b'openat(AT_FDCWD, "/tmp/fixture/root/probe.txt", O_RDONLY) = 3</tmp/fixture/root/probe.txt>\n'
    assert content_audit(case, measured(good_stdout, trace=safe))['status'] == 'pass'
