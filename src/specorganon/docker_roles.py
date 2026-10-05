"""Private host transport for isolated native roles and uncredentialed tests.

No credentials/sessions are copied. Original authorized profiles are mounted only
for their native role. A created container's handle is persisted before start;
an interrupted attachment without a host receipt remains uncertain and is never
restarted. Reconciliation kills that exact owned container, retaining its files.
The trusted operator owns the journals and Docker daemon; hashes do not attest it.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import time

from .ledger import strict_json_loads, _open_regular_file
from .role_jobs import JobStore, JobError, UncertainJob, canonical, digest, _read, _json, _write, _safe


class DockerRoleError(ValueError):
    pass


class DockerRoles:
    def __init__(self, root, *, native_image, test_image, source_root, public_catalog,
                 author_provider='codex', author_model='gpt-6.1-sol',
                 reviewer_provider='gemini', reviewer_model='gemini-3.1-pro-high',
                 codex_volume='specorganon-lab_codex-home', gemini_profile='/home/stev/.gemini',
                 gemini_executable='/home/stev/.local/bin/agy', seccomp=None, test_timeout_seconds=120):
        self.root = _safe(root); self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.source = _safe(source_root); self.catalog = _safe(public_catalog)
        self.images = {'native': self._image(native_image), 'test': self._image(test_image)}
        self.routes = {'author': (author_provider, author_model), 'review': (reviewer_provider, reviewer_model)}
        if any(provider not in {'codex', 'gemini'} or type(model) is not str or not model for provider, model in self.routes.values()):
            raise DockerRoleError('unsupported explicit native route')
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', codex_volume) is None:
            raise DockerRoleError('invalid original Codex volume name')
        self.volume = codex_volume; self.gemini_profile = _safe(gemini_profile)
        self.gemini_executable = _safe(gemini_executable)
        self.seccomp = _safe(seccomp) if seccomp is not None else None
        if type(test_timeout_seconds) is not int or not 1 <= test_timeout_seconds <= 120:
            raise DockerRoleError('test timeout must be 1..120 seconds')
        self.test_timeout = test_timeout_seconds
        self.store = JobStore(self.root / 'host-journal', max_jobs=80, max_elapsed_seconds=6000)
        policy = {'schema': 2, 'images': self.images, 'routes': self.routes, 'test_timeout_seconds': self.test_timeout,
                  'source_root': str(self.source), 'public_catalog_sha256': digest(_read(self.catalog)),
                  'codex_original_volume': self.volume, 'gemini_original_profile': str(self.gemini_profile),
                  'gemini_executable_sha256': digest(_read(self.gemini_executable, 536870912)),
                  'seccomp_sha256': digest(_read(self.seccomp)) if self.seccomp else None}
        path = self.root / 'transport-policy.json'
        if path.exists():
            if _json(path) != strict_json_loads(canonical(policy).decode()):
                raise DockerRoleError('transport policy changed; use an explicitly versioned run')
        else: _write(path, policy)

    @staticmethod
    def _cli(argv, *, allow_failure=False):
        command = ['/usr/bin/docker', *argv]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        streams = {'stdout': bytearray(), 'stderr': bytearray()}; selector = selectors.DefaultSelector()
        deadline = time.monotonic() + 15
        try:
            for name in streams:
                pipe = getattr(process, name); os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise DockerRoleError('Docker control deadline exceeded')
                for key, _ in selector.select(min(remaining, .05)):
                    raw = os.read(key.fd, 65536)
                    if not raw: selector.unregister(key.fileobj); continue
                    if len(streams[key.data]) + len(raw) > 2097152:
                        raise DockerRoleError('Docker control response oversized')
                    streams[key.data].extend(raw)
            result = subprocess.CompletedProcess(command, process.returncode, bytes(streams['stdout']), bytes(streams['stderr']))
        finally:
            selector.close()
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(timeout=2)
            for pipe in (process.stdout, process.stderr): pipe.close()
        if result.returncode and not allow_failure: raise DockerRoleError('Docker control command failed: ' + argv[0])
        return result

    @classmethod
    def _image(cls, ref):
        if type(ref) is not str or re.fullmatch(r'sha256:[0-9a-f]{64}', ref) is None:
            raise DockerRoleError('inspect and pin immutable image ID before constructing transport')
        actual = cls._cli(['image', 'inspect', ref, '--format', '{{.Id}}']).stdout.decode().strip()
        if actual != ref: raise DockerRoleError('inspected image identity diverged')
        return ref

    @contextmanager
    def _lock(self):
        fd = _open_regular_file(self.root / '.transport.lock', os.O_RDWR | os.O_CREAT)
        try: fcntl.flock(fd, fcntl.LOCK_EX); yield
        finally: os.close(fd)

    @staticmethod
    def _inventory(path):
        return {str(p.relative_to(path)): digest(_read(p, 2097152))
                for p in sorted(path.rglob('*')) if p.is_file()}

    def _prepare(self, job_id, role, request, files=None):
        if type(job_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', job_id) is None:
            raise DockerRoleError('invalid persistent job ID')
        folder = self.root / 'jobs' / job_id
        request_raw = canonical(request)
        if len(request_raw) > 128000: raise DockerRoleError('native request exceeds input limit')
        plan_path = folder / 'launch.json'
        if folder.exists():
            if not plan_path.exists(): raise UncertainJob('job preparation interrupted; inspect, do not replace')
            plan = _json(plan_path)
            if plan['role'] != role or plan['request_sha256'] != digest(request_raw):
                raise DockerRoleError('persistent job request/role changed')
            if self._inventory(folder / 'input') != plan['input_manifest']:
                raise DockerRoleError('prepared input bytes changed')
            return folder, plan
        folder.mkdir(parents=True, mode=0o700)
        inp = folder / 'input'; inp.mkdir(mode=0o700); (folder / 'output').mkdir(mode=0o700)
        (inp / 'request.json').write_bytes(request_raw)
        image = self.images['test' if role == 'test' else 'native']
        provider = None; model = None
        if role != 'test':
            provider, model = self.routes[role]
            shutil.copy2(self.source / 'scripts/controller_native_role.py', inp / 'bridge.py')
            shutil.copytree(self.source / 'src/specorganon', inp / 'library/specorganon', ignore=shutil.ignore_patterns('__pycache__'))
            if provider == 'codex': shutil.copy2(self.catalog, inp / 'public-models.json')
        else:
            from .software_controller import safe_file
            for name, text in files.items():
                target = inp / 'delivery' / safe_file(name); target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                target.write_text(text)
        label = digest(canonical({'root': str(self.root), 'job_id': job_id}))[:24]
        name = 'specorganon-role-' + label
        args = ['create', '--name', name, '--label', 'specorganon.run=' + label, '--read-only', '--cap-drop=ALL',
                '--security-opt', 'no-new-privileges', '--memory', '1g', '--cpus', '2', '--pids-limit', '128',
                '--tmpfs', '/tmp:rw,nosuid,size=256m', '--mount', f'type=bind,src={inp},dst=/input,readonly',
                '--mount', f'type=bind,src={folder / "output"},dst=/output', '-e', 'TMPDIR=/output']
        if role == 'test':
            args += ['--network', 'none', '-e', 'HOME=/output', '-w', '/input/delivery', '--entrypoint', '', image, *request['argv']]
        else:
            if self.seccomp: args += ['--security-opt', 'seccomp=' + str(self.seccomp)]
            if provider == 'codex': args += ['--mount', f'type=volume,src={self.volume},dst=/home/codex/.codex']
            else:
                args += ['--mount', f'type=bind,src={self.gemini_profile},dst=/home/stev/.gemini',
                         '--mount', f'type=bind,src={self.gemini_executable},dst=/usr/local/bin/agy,readonly', '-e', 'HOME=/home/stev']
            args += ['-e', 'OPENAI_API_KEY=', '-e', 'PYTHONPATH=/input/library', '-e', 'SPECORGANON_ROLE_IMAGE_ID=' + image,
                     '-w', '/input', '--entrypoint', '/opt/specorganon/.venv/bin/python', image,
                     '/input/bridge.py', '--provider', provider, '--model', model, '--request', '/input/request.json', '--output-dir', '/output']
            if provider == 'codex': args += ['--model-catalog', '/input/public-models.json']
        plan = {'schema': 1, 'job_id': job_id, 'role': role, 'provider': provider, 'model': model,
                'request_sha256': digest(request_raw), 'image_id': image, 'name': name, 'label': label,
                'create_argv': args, 'container_id': None, 'input_manifest': self._inventory(inp)}
        # Persist the name/intent first. A crash after Docker create is reconciled
        # by that exact name and label; no second container or native role call.
        _write(plan_path, plan)
        return folder, plan

    def _inspect(self, plan):
        result = self._cli(['inspect', plan['name']], allow_failure=True)
        if result.returncode: return None
        records = strict_json_loads(result.stdout.decode())
        if type(records) is not list or len(records) != 1: raise DockerRoleError('invalid Docker inspection')
        value = records[0]
        if value['Config']['Labels'].get('specorganon.run') != plan['label'] or value['Image'] != plan['image_id']:
            raise DockerRoleError('container ownership/image binding diverged')
        return value

    def _execute(self, job_id, role, request, files=None):
        folder, plan = self._prepare(job_id, role, request, files)
        record = self._inspect(plan)
        if plan['container_id'] is None:
            if record is None:
                created = self._cli(plan['create_argv']).stdout.decode().strip()
                if re.fullmatch(r'[0-9a-f]{64}', created) is None: raise DockerRoleError('invalid created container handle')
                plan['container_id'] = created
            else: plan['container_id'] = record['Id']
            _write(folder / 'launch.json', plan); record = self._inspect(plan)
        if record is None or record['Id'] != plan['container_id']:
            raise UncertainJob('recorded container handle missing; never recreate native call')
        if (record['State']['Status'] != 'created'
                and not (self.store.root / job_id / 'receipt.json').exists()
                and not (self.store.root / job_id / 'started.json').exists()):
            self.reconcile(job_id); raise UncertainJob('container previously started without journal proof; never restart')
        if role == 'test' and (record['Config']['Cmd'] != request['argv'] or record['Config']['Entrypoint'] not in (None, [])):
            raise DockerRoleError('test container command differs from exact subject argv')
        argv = ['/usr/bin/docker', 'start', '--attach', plan['container_id']]
        try:
            result = self.store.execute(job_id, argv, request, cwd=self.root,
                timeout_seconds=self.test_timeout if role == 'test' else 180,
                metadata={'role': role, 'provider': plan['provider'], 'model': plan['model'],
                          'image_id': plan['image_id'], 'container_id': plan['container_id'],
                          'input_manifest': plan['input_manifest']},
                cancel_argv=['/usr/bin/docker', 'kill', plan['container_id']])
        except UncertainJob:
            # No inference from exit0/container state closes the lost host receipt.
            self.reconcile(job_id)
            raise
        if self._inventory(folder / 'input') != plan['input_manifest']:
            raise DockerRoleError('role/test input changed after dispatch')
        observed = self._inspect(plan)
        if observed is None: raise UncertainJob('terminal container handle disappeared; no outcome promotion')
        if observed['State']['Running']:
            self.reconcile(job_id); raise UncertainJob('owned container still live after attachment; no terminal promotion')
        _write(folder / 'terminal-container.json', {'id': plan['container_id'], 'exit_code': observed['State']['ExitCode'],
                                                  'image_id': observed['Image'], 'oom_killed': observed['State']['OOMKilled']})
        if (result['receipt']['exit_code'] != observed['State']['ExitCode']
                and not result['receipt']['timed_out'] and not result['receipt']['truncated_streams']):
            raise DockerRoleError('attachment and container exit code diverged without bounded cancellation')
        if observed['State']['OOMKilled']: raise DockerRoleError('container OOM killed; preserve failed execution')
        return folder, plan, result

    def reconcile(self, job_id):
        folder = self.root / 'jobs' / job_id; plan = _json(folder / 'launch.json'); value = self._inspect(plan)
        if value is None: outcome = 'handle_missing_uncertain'
        elif value['State']['Running']:
            self._cli(['kill', value['Id']], allow_failure=True)
            value = self._inspect(plan)
            if value is not None and value['State']['Running']: raise DockerRoleError('owned container could not be stopped')
            outcome = 'owned_container_killed_execution_uncertain'
        else: outcome = 'owned_container_stopped_execution_uncertain'
        _write(folder / 'reconciliation.json', {'schema': 1, 'outcome': outcome, 'name': plan['name'],
                                               'native_restarted': False, 'acceptance': False})
        return outcome

    def call(self, job_id, role, request):
        with self._lock():
            folder, plan, job = self._execute(job_id, role, request)
            receipt = job['receipt']
            if receipt['exit_code'] or receipt['timed_out'] or receipt['truncated_streams']:
                raise DockerRoleError('native role failed/inconclusive; preserve without replacement')
            packet = strict_json_loads(job['stdout'].decode())
            if packet.get('request_sha256') != plan['request_sha256'] or packet.get('provider') != plan['provider'] or packet.get('model') != plan['model']:
                raise DockerRoleError('native bridge request/provider/model binding diverged')
            return {**packet, 'actor': ('agent:' if role == 'author' else 'reviewer:') + plan['provider'] + '-isolated-' + role,
                    'receipt_ref': str(self.store.root / job_id / 'receipt.json'), 'provenance': 'native'}

    def measure(self, job_id, argv, files):
        if (type(argv) is not list or not argv or any(type(v) is not str or not v or '\0' in v for v in argv)
                or not argv[0].startswith('/') or len(canonical(argv)) > 16384):
            raise DockerRoleError('test needs bounded explicit absolute argv')
        request = {'schema': 1, 'argv': argv, 'delivery_tree_sha256': digest(canonical(files))}
        with self._lock():
            folder, plan, job = self._execute(job_id, 'test', request, files)
            measured = job['receipt']; result = {**measured, 'subject_argv': argv,
                'attachment_exit_code': measured['exit_code'],
                'exit_code': _json(folder / 'terminal-container.json')['exit_code'],
                'test_job_ref': str(self.store.root / job_id / 'receipt.json'),
                'delivery_tree_sha256': request['delivery_tree_sha256'], 'image_id': plan['image_id'],
                'container_id': plan['container_id'], 'provenance': 'actual_isolated_container',
                'passed': measured['exit_code'] == 0 and not measured['timed_out'] and not measured['truncated_streams']}
            _write(folder / 'measured-test.json', result)
            return result

    def verify_test(self, data, files, *, require_passed=True, require_current=True):
        path = _safe(data['test_job_ref'])
        if path.parent.parent != self.store.root: raise DockerRoleError('test receipt lies outside this private journal')
        job_id = path.parent.name; receipt = _json(path); actual = _json(self.root / 'jobs' / job_id / 'measured-test.json')
        terminal = _json(self.root / 'jobs' / job_id / 'terminal-container.json')
        self.store._validate_receipt(path.parent, job_id, receipt)
        if ((require_current and actual['delivery_tree_sha256'] != digest(canonical(files)))
                or data.get('delivery_tree_sha256', actual['delivery_tree_sha256']) != actual['delivery_tree_sha256']
                or actual['subject_argv'] != data['argv']
                or (require_passed and actual['passed'] is not True) or actual['test_job_ref'] != str(path)
                or actual['attachment_exit_code'] != receipt['exit_code'] or actual['exit_code'] != terminal['exit_code']
                or any(actual[k] != receipt[k] for k in ('timed_out', 'stdout_sha256', 'stderr_sha256'))):
            raise DockerRoleError('test receipt/current delivery diverged')
        for name in ('stdout', 'stderr'):
            if digest(_read(path.parent / (name + '.bin'))) != receipt[name + '_sha256']:
                raise DockerRoleError('test measured stream changed')
        return True
