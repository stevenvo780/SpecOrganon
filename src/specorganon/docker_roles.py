"""Private host transport for isolated native roles and uncredentialed tests.

No credentials/sessions are copied. Original authorized profiles are mounted only
for their native role. A created container's handle is persisted before start;
an interrupted attachment without a host receipt remains uncertain and is never
restarted. Reconciliation kills that exact owned container, retaining its files.
The trusted operator owns the journals and Docker daemon; hashes do not attest it.
Control calls each have a 15-second deadline. JobStore checks its 6000-second
elapsed admission budget (including prior preparation) before payload dispatch;
it does not reserve Docker preparation or impose a hard end-to-end deadline.
Denied payload admission can leave an owned never-started container for diagnosis.
Full cohort wall time, rather than receipt-duration sums, measures efficiency.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time
import uuid

from .ledger import strict_json_loads, _open_regular_file
from .role_jobs import JobStore, JobError, UncertainJob, canonical, digest, _read, _json, _write, _safe


class DockerRoleError(ValueError):
    pass


class DockerControlDeadlineError(DockerRoleError):
    """Only the CLI deadline expired; the daemon operation may have completed."""

    def __init__(self, operation):
        self.operation = operation
        super().__init__('Docker control deadline exceeded: ' + operation)


class DockerRoles:
    _CODEX_REASONING_EFFORTS = ('low', 'medium', 'high', 'xhigh')

    def __init__(self, root, *, native_image, test_image, source_root, public_catalog,
                 author_provider='codex', author_model='gpt-6.1-sol',
                 reviewer_provider='gemini', reviewer_model='gemini-3.1-pro-high',
                 codex_volume='specorganon-lab_codex-home', gemini_profile='/home/stev/.gemini',
                 gemini_executable='/home/stev/.local/bin/agy', seccomp=None, test_timeout_seconds=120,
                 codex_reasoning_effort='low', source_bindings=None):
        self.root = _safe(root); self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.source = _safe(source_root); self.catalog = _safe(public_catalog)
        self.images = {'native': self._image(native_image), 'test': self._image(test_image)}
        self.routes = {'author': (author_provider, author_model), 'review': (reviewer_provider, reviewer_model)}
        if any(provider not in {'codex', 'gemini'} or type(model) is not str or not model for provider, model in self.routes.values()):
            raise DockerRoleError('unsupported explicit native route')
        if (type(codex_reasoning_effort) is not str
                or codex_reasoning_effort not in self._CODEX_REASONING_EFFORTS):
            raise DockerRoleError('codex_reasoning_effort must be one of low/medium/high/xhigh')
        self.codex_reasoning_effort = codex_reasoning_effort
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', codex_volume) is None:
            raise DockerRoleError('invalid original Codex volume name')
        self.volume = codex_volume; self.gemini_profile = _safe(gemini_profile)
        self.gemini_executable = _safe(gemini_executable)
        self.seccomp = _safe(seccomp) if seccomp is not None else None
        if type(test_timeout_seconds) is not int or not 1 <= test_timeout_seconds <= 120:
            raise DockerRoleError('test timeout must be 1..120 seconds')
        self.test_timeout = test_timeout_seconds
        self.store = JobStore(self.root / 'host-journal', max_jobs=80, max_elapsed_seconds=6000)
        self.source_bindings = dict(source_bindings) if source_bindings is not None else None
        sources = self._native_source_bytes()
        inputs = {'public-models.json': _read(self.catalog)}
        if self.seccomp:
            inputs['seccomp.json'] = _read(self.seccomp)
        if self.source_bindings is not None:
            registered = dict(sources)
            registered[str(self.catalog.relative_to(self.source))] = inputs['public-models.json']
            if self.seccomp:
                registered[str(self.seccomp.relative_to(self.source))] = inputs['seccomp.json']
            if any(self.source_bindings.get(name) != digest(raw) for name,raw in registered.items()):
                raise DockerRoleError('transport input differs from registered source binding')
        self.native_sources = {name:digest(raw) for name,raw in sources.items()}
        self.launch_input_sha256 = {name:digest(raw) for name,raw in inputs.items()}
        policy = {'schema': 5, 'create_recovery': 'owned-never-started-after-create-deadline-v1',
                  'images': self.images, 'routes': self.routes, 'test_timeout_seconds': self.test_timeout,
                  'source_root': str(self.source), 'public_catalog_sha256': self.launch_input_sha256['public-models.json'],
                  'native_source_sha256': self.native_sources,
                  'registered_source_bindings_sha256': digest(canonical(self.source_bindings)) if self.source_bindings is not None else None,
                  'codex_original_volume': self.volume, 'gemini_original_profile': str(self.gemini_profile),
                  'gemini_executable_sha256': digest(_read(self.gemini_executable, 536870912)),
                  'codex_reasoning_effort': self.codex_reasoning_effort,
                  'seccomp_sha256': self.launch_input_sha256.get('seccomp.json')}
        path = self.root / 'transport-policy.json'
        if path.exists():
            existing = _json(path)
            if type(existing) is not dict or existing.get('schema') != 5:
                raise DockerRoleError('transport schema5 required; previous schema cannot resume silently')
            if existing != strict_json_loads(canonical(policy).decode()):
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
                if remaining <= 0: raise DockerControlDeadlineError(argv[0])
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

    def _native_source_bytes(self):
        paths=[self.source/'scripts/controller_native_role.py',
               *sorted((self.source/'src/specorganon').glob('*.py'))]
        if self.source/'src/specorganon/__init__.py' not in paths:
            raise DockerRoleError('native library sources missing')
        return {str(p.relative_to(self.source)):_read(p) for p in paths}

    def _bound_native_source_bytes(self):
        raw=self._native_source_bytes()
        if {name:digest(value) for name,value in raw.items()} != self.native_sources:
            raise DockerRoleError('native source changed; use a versioned run')
        return raw

    def _prepare(self, job_id, role, request, files=None):
        if type(job_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', job_id) is None:
            raise DockerRoleError('invalid persistent job ID')
        folder = self.root / 'jobs' / job_id
        request_raw = canonical(request)
        if len(request_raw) > 128000: raise DockerRoleError('native request exceeds input limit')
        sources = self._bound_native_source_bytes()
        launch_inputs = {'public-models.json': _read(self.catalog)}
        if self.seccomp:
            launch_inputs['seccomp.json'] = _read(self.seccomp)
        if {name:digest(raw) for name,raw in launch_inputs.items()} != self.launch_input_sha256:
            raise DockerRoleError('registered launch input changed before preparation')
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
            # Copy the SAME bytes whose hashes were checked, not a second
            # filesystem read after validation. No credentials/profile data.
            (inp / 'bridge.py').write_bytes(sources['scripts/controller_native_role.py'])
            package=inp/'library/specorganon';package.mkdir(parents=True)
            for name,raw in sources.items():
                if name.startswith('src/specorganon/'):
                    (package/Path(name).name).write_bytes(raw)
            if provider == 'codex': (inp / 'public-models.json').write_bytes(launch_inputs['public-models.json'])
            if self.seccomp: (inp / 'seccomp.json').write_bytes(launch_inputs['seccomp.json'])
        else:
            from .software_controller import safe_file
            for name, text in files.items():
                target = inp / 'delivery' / safe_file(name); target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                target.write_text(text)
        label = digest(canonical({'root': str(self.root), 'job_id': job_id}))[:24]
        nonce = uuid.uuid4().hex
        creation_not_before = datetime.now(timezone.utc).isoformat()
        name = 'specorganon-role-' + label
        args = ['create', '--name', name, '--label', 'specorganon.run=' + label,
                '--label', 'specorganon.execution_nonce=' + nonce, '--read-only', '--cap-drop=ALL',
                '--security-opt', 'no-new-privileges', '--memory', '1g', '--cpus', '2', '--pids-limit', '128',
                '--tmpfs', '/tmp:rw,nosuid,size=256m', '--mount', f'type=bind,src={inp},dst=/input,readonly',
                '--mount', f'type=bind,src={folder / "output"},dst=/output', '-e', 'TMPDIR=/output']
        if role == 'test':
            args += ['--network', 'none', '-e', 'HOME=/output', '-w', '/input/delivery', '--entrypoint', '', image, *request['argv']]
        else:
            if self.seccomp: args += ['--security-opt', 'seccomp=' + str(inp / 'seccomp.json')]
            if provider == 'codex': args += ['--mount', f'type=volume,src={self.volume},dst=/home/codex/.codex']
            else:
                args += ['--mount', f'type=bind,src={self.gemini_profile},dst=/home/stev/.gemini',
                         '--mount', f'type=bind,src={self.gemini_executable},dst=/usr/local/bin/agy,readonly', '-e', 'HOME=/home/stev']
            args += ['-e', 'OPENAI_API_KEY=', '-e', 'PYTHONPATH=/input/library', '-e', 'SPECORGANON_ROLE_IMAGE_ID=' + image,
                     '-w', '/input', '--entrypoint', '/opt/specorganon/.venv/bin/python', image,
                     '/input/bridge.py', '--provider', provider, '--model', model, '--request', '/input/request.json', '--output-dir', '/output']
            if provider == 'codex':
                args += ['--model-catalog', '/input/public-models.json',
                         '--codex-reasoning-effort', self.codex_reasoning_effort]
        plan = {'schema': 2, 'job_id': job_id, 'role': role, 'provider': provider, 'model': model,
                'execution_nonce': nonce, 'creation_not_before': creation_not_before,
                'request_sha256': digest(request_raw), 'image_id': image, 'name': name, 'label': label,
                'create_argv': args, 'container_id': None, 'control_recovery_sha256': None,
                'input_manifest': self._inventory(inp),
                'codex_reasoning_effort': self.codex_reasoning_effort if provider == 'codex' else None}
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
        labels = value['Config']['Labels']
        if (plan.get('schema') != 2
                or type(plan.get('execution_nonce')) is not str
                or re.fullmatch(r'[0-9a-f]{32}', plan['execution_nonce']) is None
                or labels.get('specorganon.run') != plan['label']
                or labels.get('specorganon.execution_nonce') != plan['execution_nonce']
                or value.get('Name') != '/' + plan['name']
                or value['Image'] != plan['image_id']):
            raise DockerRoleError('container ownership/image binding diverged')
        try:
            created = datetime.fromisoformat(value['Created'].replace('Z', '+00:00'))
            intent = datetime.fromisoformat(plan['creation_not_before'])
            if created.tzinfo is None or intent.tzinfo is None or created < intent:
                raise ValueError('creation predates persisted intent')
        except (KeyError, TypeError, ValueError) as exc:
            raise DockerRoleError('container creation time differs from persisted intent') from exc
        return value

    @staticmethod
    def _creation_attempt(plan):
        return {'schema': 1, 'name': plan['name'], 'label': plan['label'],
                'execution_nonce': plan['execution_nonce'], 'image_id': plan['image_id'],
                'creation_not_before': plan['creation_not_before'],
                'create_argv_sha256': digest(canonical(plan['create_argv']))}

    def _never_started_handle(self, job_id, value):
        state = value.get('State', {}) if value is not None else {}
        container_id = value.get('Id') if value is not None else None
        journal = self.store.root / job_id
        if (type(container_id) is not str or re.fullmatch(r'[0-9a-f]{64}', container_id) is None
                or state.get('Status') != 'created'
                or any(state.get(key) is not False for key in ('Running', 'Restarting', 'Dead'))
                or state.get('StartedAt') != '0001-01-01T00:00:00Z'
                or any((journal / name).exists() for name in ('started.json', 'receipt.json'))):
            raise UncertainJob('creation has no owned never-started container proof')
        return container_id

    @staticmethod
    def _recovery_observation(plan, container_id):
        return {'schema': 1, 'scope': 'control response recovery only; no role outcome or acceptance',
                'operation': 'create', 'deadline_seconds': 15, 'name': plan['name'],
                'label': plan['label'], 'image_id': plan['image_id'], 'container_id': container_id,
                'execution_nonce': plan['execution_nonce'], 'creation_not_before': plan['creation_not_before'],
                'state': {'Status': 'created', 'Running': False, 'Restarting': False, 'Dead': False,
                          'StartedAt': '0001-01-01T00:00:00Z'},
                'create_repeated': False, 'execution_started_at_observation': False}

    def _recover_created(self, job_id, folder, plan, cause):
        # Never repeat create, infer a completed role, or restart a container.
        # Inspection retains its own 15-second deadline and ownership guards.
        if cause.operation != 'create':
            raise cause
        if (not (folder / 'create-attempt.json').exists()
                or _json(folder / 'create-attempt.json') != self._creation_attempt(plan)):
            raise UncertainJob('create deadline lacks bound persisted attempt') from cause
        value = self._inspect(plan)
        container_id = self._never_started_handle(job_id, value)
        observation = self._recovery_observation(plan, container_id)
        path = folder / 'control-recovery.json'
        if path.exists():
            if _json(path) != observation:
                raise UncertainJob('create recovery observation changed')
        else:
            _write(path, observation)
        return container_id

    def _execute(self, job_id, role, request, files=None):
        folder, plan = self._prepare(job_id, role, request, files)
        attempt = folder / 'create-attempt.json'
        recovery = folder / 'control-recovery.json'
        if attempt.exists() and _json(attempt) != self._creation_attempt(plan):
            raise UncertainJob('persisted creation attempt changed')
        if plan['container_id'] is not None:
            if not attempt.exists():
                raise UncertainJob('recorded handle lacks persisted creation attempt')
            expected = plan.get('control_recovery_sha256')
            if (recovery.exists() != (expected is not None)
                    or recovery.exists() and (digest(_read(recovery)) != expected
                        or _json(recovery) != self._recovery_observation(plan, plan['container_id']))):
                raise UncertainJob('historical create recovery binding changed')
        record = self._inspect(plan)
        if plan['container_id'] is None:
            if (folder / 'control-recovery.json').exists():
                plan['container_id'] = self._recover_created(job_id, folder, plan, DockerControlDeadlineError('create'))
            elif record is None:
                if attempt.exists():
                    raise UncertainJob('creation previously attempted; missing handle must never be recreated')
                # A crash immediately after this write still consumes the one
                # creation opportunity. Missing proof cannot authorize a retry.
                _write(attempt, self._creation_attempt(plan))
                try:
                    created = self._cli(plan['create_argv']).stdout.decode().strip()
                except DockerControlDeadlineError as exc:
                    created = self._recover_created(job_id, folder, plan, exc)
                if re.fullmatch(r'[0-9a-f]{64}', created) is None: raise DockerRoleError('invalid created container handle')
                plan['container_id'] = created
            else:
                if not attempt.exists():
                    raise UncertainJob('existing container lacks persisted creation attempt')
                plan['container_id'] = self._never_started_handle(job_id, record)
            plan['control_recovery_sha256'] = digest(_read(recovery)) if recovery.exists() else None
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
