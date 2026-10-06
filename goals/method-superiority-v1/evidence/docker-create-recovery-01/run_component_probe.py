"""Real uncredentialed Docker with injected create-response loss, no model calls."""
import json
from pathlib import Path
import time

from specorganon.docker_roles import DockerRoles, DockerControlDeadlineError
from specorganon.role_jobs import UncertainJob, _json, digest, canonical

SOURCE = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
ROOT = Path('/datos/workspaces/personal/specorganon-validation/method-superiority-v1/docker-create-recovery-04')
IMAGE = 'sha256:6d196a4a021b872e2ea7d799e1797834e23b570e635bd640095f4521cca04ce2'
ARGV = ['/opt/specorganon/venv/bin/python', '-E', '-s', '-B', '/input/delivery/probe.py']
FILES = {'probe.py': 'from pathlib import Path\np=Path("/output/count.txt")\np.write_text(str(int(p.read_text())+1) if p.exists() else "1")\nprint("counter="+p.read_text())\n'}


def main():
    # An existing run is never overwritten or silently rerun.
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=False)
    (ROOT/'synthetic-executable').write_text('fixture, never invoked')
    (ROOT/'synthetic-profile').mkdir()
    rows = []
    for mode in ('created', 'already-executed', 'crash-before-handle'):
        t = DockerRoles(ROOT/mode, native_image=IMAGE, test_image=IMAGE, source_root=SOURCE,
                        public_catalog=SOURCE/'experiments/software_comparison_v3/public-models.json',
                        gemini_executable=ROOT/'synthetic-executable', gemini_profile=ROOT/'synthetic-profile')
        original_cli = t._cli; original_recover = t._recover_created
        create_calls = 0; started = time.monotonic(); job_id = 'probe'
        def lost_response(argv, **kwargs):
            nonlocal create_calls
            result = original_cli(argv, **kwargs)
            if argv[0] == 'create':
                create_calls += 1
                if mode == 'already-executed':
                    # Simulate an unexpected start before the controller can prove nonexecution.
                    original_cli(['start', '--attach', result.stdout.decode().strip()])
                raise DockerControlDeadlineError('create')
            return result
        t._cli = lost_response
        class InjectedCrash(Exception): pass
        def crash_before_handle(*args):
            original_recover(*args)
            raise InjectedCrash('after recovery observation, before launch CID persistence')
        if mode == 'crash-before-handle': t._recover_created = crash_before_handle
        try:
            if mode == 'already-executed':
                try: t.measure(job_id, ARGV, FILES)
                except UncertainJob: pass
                else: raise AssertionError('executed container must not be promoted/restarted')
                assert not (t.store.root/job_id/'receipt.json').exists()
                assert not (t.root/'jobs'/job_id/'control-recovery.json').exists()
                measured = None
            else:
                if mode == 'crash-before-handle':
                    try: t.measure(job_id, ARGV, FILES)
                    except InjectedCrash: pass
                    else: raise AssertionError('injected interruption must be visible')
                    plan = _json(t.root/'jobs'/job_id/'launch.json')
                    assert plan['container_id'] is None and t._inspect(plan)['State']['Status'] == 'created'
                    assert not (t.store.root/job_id/'started.json').exists()
                    t._recover_created = original_recover
                measured = t.measure(job_id, ARGV, FILES)
                assert measured['passed'] is True
                assert t.measure(job_id, ARGV, FILES) == measured
                assert t.verify_test({'argv': ARGV, 'test_job_ref': measured['test_job_ref']}, FILES)
                observation = _json(t.root/'jobs'/job_id/'control-recovery.json')
                assert observation['execution_started_at_observation'] is False
            folder = t.root/'jobs'/job_id
            plan = _json(folder/'launch.json'); value = t._inspect(plan)
            assert value['HostConfig']['NetworkMode'] == 'none' and value['HostConfig']['ReadonlyRootfs'] is True
            assert not any(m['Destination'] in {'/home/codex/.codex','/home/stev/.gemini','/var/run/docker.sock'} for m in value['Mounts'])
            assert (folder/'output/count.txt').read_text() == '1' and create_calls == 1
            rows.append({'mode': mode, 'actual_container_id': value['Id'], 'image_id': value['Image'],
                         'create_calls': create_calls, 'actual_counter': 1,
                         'closed_host_receipt': measured is not None,
                         'uncertain_execution_refused': mode == 'already-executed',
                         'wall_seconds': time.monotonic()-started,
                         'records_sha256': {str(p.relative_to(t.root)): digest(p.read_bytes())
                                            for p in sorted(t.root.rglob('*')) if p.is_file()}})
        finally:
            p = t.root/'jobs'/job_id/'launch.json'
            if p.exists():
                value = t._inspect(_json(p))
                if value is not None: original_cli(['rm', '--force', value['Id']])
    result = {'schema': 1, 'scope': 'three real uncredentialed Docker controls with injected CLI response loss; no model calls or phase acceptance',
              'deadline_was_injected_after_actual_create': True, 'natural_15_second_timeout_reproduced': False,
              'source_sha256': {name: digest((SOURCE/name).read_bytes()) for name in
                                ('src/specorganon/docker_roles.py','src/specorganon/role_jobs.py',
                                 'src/specorganon/__init__.py','pyproject.toml','uv.lock')},
              'probe_sha256': digest(Path(__file__).read_bytes()), 'rows': rows}
    (EVIDENCE/'component-receipt-04.json').write_bytes(canonical(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
