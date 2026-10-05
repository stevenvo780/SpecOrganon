"""Real bounded processes for the controller journal; no model judgments here."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from specorganon.role_jobs import JobError, JobStore, UncertainJob


def command(counter):
    code = "from pathlib import Path;import sys;p=Path(sys.argv[1]);p.write_text(str(int(p.read_text())+1) if p.exists() else '1');print('done');print('diagnostic',file=sys.stderr)"
    return [sys.executable, "-c", code, str(counter)]


def test_closed_job_reuses_measured_streams_without_running_again(tmp_path):
    store = JobStore(tmp_path / "jobs")
    counter = tmp_path / "counter"
    args = command(counter)
    first = store.execute("author-01", args, {"phase": "frame"}, cwd=tmp_path, timeout_seconds=5)
    raw = (store.root / "author-01/receipt.json").read_bytes()
    second = store.execute("author-01", args, {"phase": "frame"}, cwd=tmp_path, timeout_seconds=5)
    assert first["reused"] is False and second["reused"] is True
    assert counter.read_text() == "1" and raw == (store.root / "author-01/receipt.json").read_bytes()
    receipt = first["receipt"]
    assert receipt["exit_code"] == 0 and receipt["timed_out"] is False
    assert receipt["stdout_sha256"] == hashlib.sha256(b"done\n").hexdigest()
    assert receipt["stderr_sha256"] == hashlib.sha256(b"diagnostic\n").hexdigest()


@pytest.mark.parametrize("change", ["request", "argv", "stream"])
def test_cached_job_rejects_changed_inputs_or_stream_before_new_execution(tmp_path, change):
    store = JobStore(tmp_path / "jobs"); counter = tmp_path / "counter"
    args = command(counter); request = {"phase": "frame"}
    store.execute("author-01", args, request, cwd=tmp_path, timeout_seconds=5)
    if change == "request": request = {"phase": "study"}
    elif change == "argv": args = args + ["changed"]
    else: (store.root / "author-01/stdout.bin").write_bytes(b"forged success")
    with pytest.raises(JobError):
        store.execute("author-01", args, request, cwd=tmp_path, timeout_seconds=5)
    assert counter.read_text() == "1"


def test_failure_counts_against_budget_and_does_not_retry(tmp_path):
    store = JobStore(tmp_path / "jobs", max_jobs=1)
    args = [sys.executable, "-c", "raise SystemExit(3)"]
    first = store.execute("failed-01", args, {}, cwd=tmp_path, timeout_seconds=5)
    assert first["receipt"]["exit_code"] == 3
    assert store.execute("failed-01", args, {}, cwd=tmp_path, timeout_seconds=5)["reused"]
    with pytest.raises(JobError, match="budget"):
        store.execute("failed-02", args, {}, cwd=tmp_path, timeout_seconds=5)
    with pytest.raises(JobError, match="policy"):
        JobStore(store.root, max_jobs=2)


def test_stream_limit_terminates_process_and_never_reports_success(tmp_path):
    store = JobStore(tmp_path / "jobs", max_stream_bytes=1024)
    args = [sys.executable, "-c", "import os,time;os.write(1,b'x'*10000);time.sleep(30)"]
    result = store.execute("loud-01", args, {}, cwd=tmp_path, timeout_seconds=5)["receipt"]
    assert result["truncated_streams"] == ["stdout"]
    assert result["exit_code"] != 0 and result["stdout_bytes"] == 1024
    assert (store.root / "loud-01/stdout.bin").stat().st_size == 1024


def test_timeout_retains_non_successful_receipt(tmp_path):
    store = JobStore(tmp_path / "jobs")
    result = store.execute("slow-01", [sys.executable, "-c", "import time;time.sleep(30)"],
                           {}, cwd=tmp_path, timeout_seconds=1)["receipt"]
    assert result["timed_out"] is True and result["exit_code"] != 0


def test_large_stdin_and_both_streams_do_not_deadlock_and_bind_the_input(tmp_path):
    store = JobStore(tmp_path / "jobs")
    code = "import os,sys;os.write(1,b'x'*80000);os.write(2,b'y'*80000);print(len(sys.stdin.buffer.read()))"
    args = [sys.executable, "-c", code]
    first = store.execute("duplex-01", args, {}, cwd=tmp_path,
                          timeout_seconds=5, stdin_bytes=b"z" * 100000)
    assert first["receipt"]["exit_code"] == 0
    assert (store.root / "duplex-01/stdout.bin").read_bytes() == b"x" * 80000 + b"100000\n"
    assert (store.root / "duplex-01/stderr.bin").read_bytes() == b"y" * 80000
    with pytest.raises(JobError):
        store.execute("duplex-01", args, {}, cwd=tmp_path,
                      timeout_seconds=5, stdin_bytes=b"changed")


def wait_for(path, predicate=lambda value: True):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if path.exists():
            try:
                value = json.loads(path.read_text()) if path.suffix == ".json" else path.read_text()
                if predicate(value): return value
            except (ValueError, OSError): pass
        time.sleep(0.02)
    raise AssertionError(f"process did not reach checkpoint {path}")


def helper(tmp_path, delay_after_receipt=False, child_sleep=False):
    script = tmp_path / "helper.py"
    script.write_text(
        "import sys,time,json\nfrom pathlib import Path\n"
        "from specorganon.role_jobs import JobStore\n"
        "from specorganon import engine\nfrom specorganon.runner import run_manifest\n"
        "root=Path(sys.argv[1]);store=JobStore(root/'jobs')\n"
        f"args={command(tmp_path / 'counter')!r}\n"
        + ("args[2]+=';import time;time.sleep(30)'\n" if child_sleep else "")
        + "result=store.execute('author-01',args,{'phase':'frame'},cwd=root,timeout_seconds=60)\n"
        + ("time.sleep(30)\n" if delay_after_receipt else "")
        + "case=root/'case'\nif not (case/'organon.json').exists():\n"
        " engine.create_case(case,'synthetic journal recovery','development','human:owner',approval_policy='local')\n"
        "manifest={'schema':1,'steps':[{'op':'put','id':'p1','kind':'problem','text':'Synthetic checkpoint control, no model acceptance','refs':[],'data':{}}]}\n"
        "run_manifest(case,manifest,'agent:synthetic-recovery')\n"
        "print(json.dumps({'reused':result['reused'],'revision':engine.get_state(case)['revision']}))\n")
    return [sys.executable, str(script), str(tmp_path)]


def test_sigkill_after_receipt_reuses_job_and_replays_put_without_duplicates(tmp_path):
    proc = subprocess.Popen(helper(tmp_path, delay_after_receipt=True), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_for(tmp_path / "jobs/author-01/receipt.json")
        proc.kill(); proc.communicate(timeout=5)
        resumed = subprocess.run(helper(tmp_path), capture_output=True, text=True, timeout=10)
        assert resumed.returncode == 0, resumed.stderr
        assert json.loads(resumed.stdout) == {"reused": True, "revision": 1}
        ledger = (tmp_path / "case/organon.json").read_bytes()
        again = subprocess.run(helper(tmp_path), capture_output=True, text=True, timeout=10)
        assert again.returncode == 0, again.stderr
        assert ledger == (tmp_path / "case/organon.json").read_bytes()
        assert (tmp_path / "counter").read_text() == "1"
    finally:
        if proc.poll() is None: proc.kill(); proc.communicate(timeout=5)


def test_sigkill_before_receipt_refuses_reexecution_of_uncertain_job(tmp_path):
    proc = subprocess.Popen(helper(tmp_path, child_sleep=True), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    started = None
    try:
        started = wait_for(tmp_path / "jobs/author-01/started.json", lambda value: value.get("pid") is not None)
        wait_for(tmp_path / "counter")
        proc.kill(); proc.communicate(timeout=5)
        store = JobStore(tmp_path / "jobs")
        with pytest.raises(UncertainJob):
            store.execute("author-01", command(tmp_path / "counter"), {"phase":"frame"}, cwd=tmp_path, timeout_seconds=60)
        assert (tmp_path / "counter").read_text() == "1"
        assert not (tmp_path / "jobs/author-01/receipt.json").exists()
    finally:
        if proc.poll() is None: proc.kill(); proc.communicate(timeout=5)
        if started:
            try: os.killpg(started["pid"], signal.SIGKILL)
            except ProcessLookupError: pass


def test_job_paths_and_symlinks_cannot_redirect_receipts(tmp_path):
    store = JobStore(tmp_path / "jobs"); outside = tmp_path / "outside"; outside.mkdir()
    (store.root / "alias").symlink_to(outside, target_is_directory=True)
    for name in ["../outside", "alias", "/absolute"]:
        with pytest.raises(JobError):
            store.execute(name, [sys.executable, "-c", "print('forbidden')"], {}, cwd=tmp_path, timeout_seconds=5)
    assert not list(outside.iterdir())


@pytest.mark.parametrize("field,value", [("exit_code", 0), ("timed_out", True), ("job_id", "other")])
def test_mutated_terminal_receipt_cannot_override_measured_failure(tmp_path, field, value):
    store = JobStore(tmp_path / "jobs")
    args = [sys.executable, "-c", "raise SystemExit(3)"]
    store.execute("failed-01", args, {}, cwd=tmp_path, timeout_seconds=5)
    path = store.root / "failed-01/receipt.json"
    receipt = json.loads(path.read_text()); receipt[field] = value; path.write_text(json.dumps(receipt))
    with pytest.raises(JobError):
        store.execute("failed-01", args, {}, cwd=tmp_path, timeout_seconds=5)


def test_returned_stream_bytes_are_the_verified_measurement(tmp_path):
    store = JobStore(tmp_path / "jobs")
    result = store.execute("author-01", command(tmp_path / "counter"), {}, cwd=tmp_path, timeout_seconds=5)
    (store.root / "author-01/stdout.bin").write_bytes(b"later mutation")
    assert result["stdout"] == b"done\n" and result["stderr"] == b"diagnostic\n"


def test_inherited_environment_change_invalidates_cached_execution(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs"); counter = tmp_path / "counter"
    monkeypatch.setenv("SPECORGANON_TEST_ENV_BINDING", "first")
    store.execute("author-01", command(counter), {}, cwd=tmp_path, timeout_seconds=5)
    monkeypatch.setenv("SPECORGANON_TEST_ENV_BINDING", "second")
    with pytest.raises(JobError):
        store.execute("author-01", command(counter), {}, cwd=tmp_path, timeout_seconds=5)
    assert counter.read_text() == "1"


def test_process_closing_pipes_is_still_supervised_until_deadline(tmp_path):
    store = JobStore(tmp_path / "jobs")
    args = [sys.executable, "-c", "import os,time;os.close(1);os.close(2);time.sleep(30)"]
    began = time.monotonic()
    result = store.execute("closed-pipes", args, {}, cwd=tmp_path, timeout_seconds=1)["receipt"]
    assert result["timed_out"] and result["exit_code"] != 0
    assert time.monotonic() - began < 3


def test_post_spawn_checkpoint_error_terminates_owned_child(tmp_path, monkeypatch):
    import specorganon.role_jobs as jobs
    store = JobStore(tmp_path / "jobs"); children = []
    original_spawn, original_write = jobs.subprocess.Popen, jobs._write
    def spawn(*args, **kwargs):
        child = original_spawn(*args, **kwargs); children.append(child); return child
    def write(path, value, **kwargs):
        if path.name == "started.json" and value.get("pid") is not None:
            raise JobError("injected checkpoint failure after spawn")
        return original_write(path, value, **kwargs)
    monkeypatch.setattr(jobs.subprocess, "Popen", spawn); monkeypatch.setattr(jobs, "_write", write)
    try:
        with pytest.raises(JobError):
            store.execute("checkpoint-error", [sys.executable, "-c", "import time;time.sleep(30)"],
                          {}, cwd=tmp_path, timeout_seconds=5)
        assert len(children) == 1 and children[0].poll() is not None
    finally:
        for child in children:
            if child.poll() is None: os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=5)


def test_clock_reboot_does_not_reset_new_job_budget(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    monkeypatch.setattr(store, "_boot_id", lambda: "changed boot")
    with pytest.raises(JobError, match="clock"):
        store.execute("never-admitted", command(tmp_path / "counter"), {}, cwd=tmp_path)
    assert not (tmp_path / "counter").exists()


def test_budget_reserves_cleanup_before_admitting_a_process(tmp_path):
    store = JobStore(tmp_path / "jobs", max_elapsed_seconds=10)
    with pytest.raises(JobError, match="budget"):
        store.execute("never-admitted", command(tmp_path / "counter"), {}, cwd=tmp_path)
    assert not (tmp_path / "counter").exists()


def test_cancellation_uses_bound_environment_cwd_and_no_input(tmp_path):
    store = JobStore(tmp_path / "jobs")
    proof = tmp_path / "cancel-proof"
    code = "import os,sys;from pathlib import Path;Path('cancel-proof').write_text(os.environ['ROLE_CANCEL_BINDING']+':'+str(len(sys.stdin.buffer.read())))"
    receipt = store.execute("timeout-cancel", [sys.executable, "-c", "import time;time.sleep(30)"], {},
        cwd=tmp_path, timeout_seconds=1, env={"ROLE_CANCEL_BINDING": "bound"},
        cancel_argv=[sys.executable, "-c", code])["receipt"]
    assert receipt["timed_out"] and receipt["cancel_exit_code"] == 0
    assert proof.read_text() == "bound:0"
