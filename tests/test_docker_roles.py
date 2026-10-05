"""Opt-in real Docker transport controls; no model calls or semantic acceptance."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from specorganon.docker_roles import DockerRoles, DockerRoleError
from specorganon.role_jobs import UncertainJob, _json, digest


pytestmark = pytest.mark.skipif(os.environ.get('SPECORGANON_DOCKER_COMPONENT_TESTS') != '1',
                               reason='requires explicit pinned Docker component experiment')
OPTIONS = {
    'native_image': 'sha256:aa4eae810628bd2b78bd48ed3059c284a497bdc7c92d81daacdfe906a3bae3ae',
    'test_image': 'sha256:3f84eb6e5c883666ffe385525864713b990ff4464ea5fc2d74cce3bee22b7710',
    'source_root': '/datos/workspaces/personal/SpecOrganon',
    'public_catalog': '/datos/workspaces/personal/specorganon-validation/autonomous-software-v1/codex0160-public-models.json',
}
PYTHON = '/opt/specorganon/venv/bin/python'
FILES = {'probe.py': 'from pathlib import Path\n'
         'p=Path("/output/count.txt"); p.write_text(str(int(p.read_text())+1) if p.exists() else "1")\n'
         'try: Path("/input/delivery/forbidden.txt").write_text("forbidden")\n'
         'except OSError: print("readonly-input")\n'
         'else: raise RuntimeError("input unexpectedly writable")\n'
         'print("actual-container-counter=1")\n'}


def cleanup(transport, job_id):
    plan = _json(transport.root / 'jobs' / job_id / 'launch.json')
    transport._cli(['rm', '--force', plan['container_id']], allow_failure=True)


def test_real_container_closed_receipt_reused_without_second_execution(tmp_path):
    transport = DockerRoles(tmp_path / 'transport', **OPTIONS)
    argv = [PYTHON, '-E', '-s', '-B', '/input/delivery/probe.py']
    try:
        measured = transport.measure('closed-probe', argv, FILES)
        assert measured['passed'] and measured['provenance'] == 'actual_isolated_container'
        folder = transport.root / 'jobs/closed-probe'
        plan = _json(folder / 'launch.json'); observed = transport._inspect(plan)
        assert observed['HostConfig']['NetworkMode'] == 'none'
        assert observed['HostConfig']['ReadonlyRootfs'] is True
        assert all(m['Destination'] not in {'/home/codex/.codex', '/home/stev/.gemini', '/var/run/docker.sock'}
                   for m in observed['Mounts'])
        assert (folder / 'output/count.txt').read_text() == '1'
        assert transport.measure('closed-probe', argv, FILES) == measured
        assert (folder / 'output/count.txt').read_text() == '1'
        data = {'argv': argv, 'test_job_ref': measured['test_job_ref']}
        assert transport.verify_test(data, FILES)
        changed = {**FILES, 'probe.py': 'print("changed executable")\n'}
        assert transport.verify_test(data, changed, require_passed=False, require_current=False)
        with pytest.raises(DockerRoleError): transport.verify_test(data, changed)
        with pytest.raises(DockerRoleError, match='changed'):
            transport.measure('closed-probe', [PYTHON, '-c', 'print("replacement")'], FILES)
        receipt = Path(measured['test_job_ref']); stdout = receipt.parent / 'stdout.bin'
        original = stdout.read_bytes(); stdout.write_bytes(b'tampered')
        with pytest.raises(ValueError): transport.verify_test(data, FILES)
        stdout.write_bytes(original)
        assert digest(original) == measured['stdout_sha256']
    finally:
        if (transport.root / 'jobs/closed-probe/launch.json').exists(): cleanup(transport, 'closed-probe')


def test_sigkill_owner_before_receipt_stops_exact_container_without_restart(tmp_path):
    root = tmp_path / 'transport'
    files = {'probe.py': FILES['probe.py'] + 'import time\ntime.sleep(90)\n'}
    argv = [PYTHON, '-E', '-s', '-B', '/input/delivery/probe.py']
    source = ('from specorganon.docker_roles import DockerRoles\n'
              f't=DockerRoles({str(root)!r}, **{OPTIONS!r})\n'
              f't.measure("interrupted-probe", {argv!r}, {files!r})\n')
    child = subprocess.Popen([sys.executable, '-c', source], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    transport = None
    try:
        marker = root / 'jobs/interrupted-probe/output/count.txt'
        deadline = time.monotonic() + 20
        while not marker.exists() and child.poll() is None and time.monotonic() < deadline: time.sleep(.05)
        assert marker.exists(), 'actual container must start before the SIGKILL control'
        os.kill(child.pid, signal.SIGKILL); child.wait(timeout=5)
        transport = DockerRoles(root, **OPTIONS)
        receipt = transport.store.root / 'interrupted-probe/receipt.json'
        assert not receipt.exists()
        with pytest.raises(UncertainJob): transport.measure('interrupted-probe', argv, files)
        plan = _json(root / 'jobs/interrupted-probe/launch.json')
        assert transport._inspect(plan)['State']['Running'] is False
        reconciliation = _json(root / 'jobs/interrupted-probe/reconciliation.json')
        assert reconciliation['native_restarted'] is False and reconciliation['acceptance'] is False
        assert marker.read_text() == '1' and not receipt.exists()
        with pytest.raises(UncertainJob): transport.measure('interrupted-probe', argv, files)
        assert marker.read_text() == '1'
    finally:
        if child.poll() is None: os.kill(child.pid, signal.SIGKILL); child.wait(timeout=5)
        if transport is not None: cleanup(transport, 'interrupted-probe')


def test_actual_test_timeout_preserves_subject_and_attachment_codes_without_success(tmp_path):
    transport = DockerRoles(tmp_path / 'transport', **OPTIONS, test_timeout_seconds=1)
    argv = [PYTHON, '-u', '-c', 'import time; print("timeout-control-started", flush=True); time.sleep(30)']
    try:
        result = transport.measure('timeout-probe', argv, {'README.md': 'Synthetic Docker timeout mechanics'})
        assert result['passed'] is False and result['timed_out'] is True
        assert result['attachment_exit_code'] == -signal.SIGKILL
        assert result['exit_code'] == 137
        receipt = Path(result['test_job_ref'])
        assert b'timeout-control-started' in (receipt.parent / 'stdout.bin').read_bytes()
        assert transport.verify_test({'argv': argv, 'test_job_ref': str(receipt)},
                                     {'README.md': 'Synthetic Docker timeout mechanics'}, require_passed=False)
        with pytest.raises(DockerRoleError):
            transport.verify_test({'argv': argv, 'test_job_ref': str(receipt)},
                                  {'README.md': 'Synthetic Docker timeout mechanics'})
        assert transport.measure('timeout-probe', argv, {'README.md': 'Synthetic Docker timeout mechanics'}) == result
    finally:
        if (transport.root / 'jobs/timeout-probe/launch.json').exists(): cleanup(transport, 'timeout-probe')
