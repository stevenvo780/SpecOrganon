"""Real SIGKILL/receipt/ledger recovery with explicitly synthetic author content."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from specorganon import engine
from specorganon.role_jobs import JobStore, canonical, digest, _json
from specorganon.software_controller import Controller


FRAME = {'schema': 1, 'manifest': {'schema': 1, 'steps': [
    {'op': 'put', 'id': 'p1', 'kind': 'problem', 'text': 'Synthetic recovery mechanics', 'refs': [], 'data': {}},
    {'op': 'put', 'id': 'a1', 'kind': 'actor', 'text': 'Synthetic test actor', 'refs': ['p1'], 'data': {}},
    {'op': 'put', 'id': 'b1', 'kind': 'boundary', 'text': 'Synthetic local mechanism only', 'refs': ['p1'], 'data': {}},
]}, 'files': {}, 'reason': 'Synthetic control; no model or semantic approval'}


class PersistentSynthetic:
    def __init__(self, root, kill_after_receipt=False):
        self.root = Path(root); self.store = JobStore(self.root / 'journal'); self.kill = kill_after_receipt
    def call(self, job_id, role, request):
        response = FRAME if role == 'author' else {
            'schema': 1, 'verdict': 'accept', 'reason': 'Synthetic mechanics only, not a model review', 'findings': []}
        counter = self.root / 'invocations.txt'
        program = ('from pathlib import Path; import json; '
                   f'p=Path({str(counter)!r}); '
                   'p.write_text(str(int(p.read_text())+1) if p.exists() else "1"); '
                   f'print(json.dumps({response!r}))')
        result = self.store.execute(job_id, [sys.executable, '-c', program], request,
                                    cwd=self.root, timeout_seconds=10)
        if self.kill: os.kill(os.getpid(), signal.SIGKILL)
        return {'result': json.loads(result['stdout']), 'request_sha256': digest(canonical(request)),
                'actor': ('agent:synthetic-recovery' if role == 'author' else 'reviewer:synthetic-recovery'),
                'receipt_ref': str(self.store.root / job_id / 'receipt.json'),
                'provenance': 'synthetic'}


def construct(case, root, kill=False):
    return Controller(case, root / 'controller', PersistentSynthetic(root / 'transport', kill),
                      contract='Synthetic recovery contract', mandate='Synthetic guard mandate', fixture_mode=True)


def test_sigkill_after_actual_role_receipt_before_puts_reuses_job_and_applies_once(tmp_path):
    case = tmp_path / 'case'; root = tmp_path / 'run'
    engine.create_case(case, 'Synthetic crash recovery', 'development', 'human:owner', approval_policy='local')
    code = ('import sys; from pathlib import Path; '
            f'sys.path.insert(0, {str(Path(__file__).parent)!r}); '
            'from test_controller_recovery import construct; '
            f'construct(Path({str(case)!r}), Path({str(root)!r}), True).step()')
    child = subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = child.communicate(timeout=20)
        assert child.returncode == -signal.SIGKILL, stderr.decode(errors='replace')
        assert engine.get_state(case)['revision'] == 0
        progress = _json(root / 'controller/progress.json')
        assert progress['pending']['status'] == 'prepared'
        job_id = progress['pending']['job_id']
        assert (root / 'transport/journal' / ('.complete-' + job_id + '.json')).is_file()
        assert (root / 'transport/invocations.txt').read_text() == '1'
        ctrl = construct(case, root)
        assert ctrl.step()['action'] == 'author'
        state = engine.get_state(case)
        assert state['revision'] == 3 and set(state['items']) == {'p1', 'a1', 'b1'}
        assert not state['phases']['frame']['accepted']
        assert (root / 'transport/invocations.txt').read_text() == '1'
        assert _json(root / 'controller/progress.json')['pending'] is None
        # Reapplying the guarded manifest is the same recovery checkpoint, not a
        # new response or favorable rerun; the runner adds no duplicate events.
        from specorganon.runner import run_manifest
        guarded = {'schema': 1, 'steps': [{**step, 'expected_version': 0,
                    'expected_deps': {ref: 1 for ref in step['refs']}} for step in FRAME['manifest']['steps']]}
        run_manifest(case, guarded, 'agent:synthetic-recovery')
        assert engine.get_state(case)['revision'] == 3
    finally:
        if child.poll() is None: os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=5)


@pytest.mark.parametrize('operation', ['put_item', 'run_manifest', 'review_phase', 'advance'])
def test_sigkill_after_engine_mutation_before_progress_commit_resumes_once(tmp_path, operation):
    case = tmp_path / 'case'; root = tmp_path / 'run'
    engine.create_case(case, 'Synthetic post-mutation recovery', 'development', 'human:owner', approval_policy='local')
    ctrl = construct(case, root)
    author_operation = operation in {'put_item', 'run_manifest'}
    if not author_operation: ctrl.step()
    target = 'controller' if operation == 'run_manifest' else 'controller.engine'
    code = (f'import sys, os, signal\nfrom pathlib import Path\nsys.path.insert(0, {str(Path(__file__).parent)!r})\n'
            'from test_controller_recovery import construct\nimport specorganon.software_controller as controller\n'
            f'original = {target}.{operation}\n'
            'def interrupted(*args, **kwargs):\n'
            '    result = original(*args, **kwargs)\n'
            '    os.kill(os.getpid(), signal.SIGKILL)\n'
            f'{target}.{operation} = interrupted\n'
            f'construct(Path({str(case)!r}), Path({str(root)!r})).step()\n')
    child = subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        _, stderr = child.communicate(timeout=20)
        assert child.returncode == -signal.SIGKILL, stderr.decode(errors='replace')
        assert _json(root / 'controller/progress.json')['pending']['status'] == 'applying'
        if operation == 'put_item': assert engine.get_state(case)['revision'] == 1
        invocations = (root / 'transport/invocations.txt').read_text()
        result = ctrl.step()
        state = engine.get_state(case)
        assert (root / 'transport/invocations.txt').read_text() == invocations
        assert state['revision'] == (3 if author_operation else 5)
        assert result['action'] == ('author' if author_operation else 'review')
        assert len(_json(root / 'controller/progress.json')['history']) == (1 if author_operation else 2)
        assert state['phases']['frame']['accepted'] is (not author_operation)
    finally:
        if child.poll() is None: os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=5)


def test_sigkill_during_file_rename_leaves_delivery_readable_and_write_resumable(tmp_path):
    case = tmp_path / 'case'; root = tmp_path / 'run'
    engine.create_case(case, 'Synthetic atomic file interruption', 'development', 'human:owner', approval_policy='local')
    code = (f'import sys, os, signal\nfrom pathlib import Path\nsys.path.insert(0, {str(Path(__file__).parent)!r})\n'
            'from test_controller_recovery import construct\n'
            f'c=construct(Path({str(case)!r}),Path({str(root)!r}))\n'
            'original=os.replace\n'
            'def interrupted(source,target,*args,**kwargs):\n'
            '    if Path(target).name == "probe.py": os.kill(os.getpid(),signal.SIGKILL)\n'
            '    return original(source,target,*args,**kwargs)\n'
            'os.replace=interrupted\n'
            'c._write_files({"source_files":{}},{"probe.py":"print(123)\\n"})\n')
    child = subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        _, stderr = child.communicate(timeout=20)
        assert child.returncode == -signal.SIGKILL, stderr.decode(errors='replace')
        ctrl = construct(case, root)
        assert ctrl._files() == {}
        ctrl._write_files({'source_files': {}}, {'probe.py': 'print(123)\n'})
        assert ctrl._files() == {'probe.py': 'print(123)\n'}
        assert engine.get_state(case)['revision'] == 0
    finally:
        if child.poll() is None: os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=5)
