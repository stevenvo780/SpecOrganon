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


class ClosedResponseContractError(DockerRoleError):
    """Closed native call with a parsed but inadmissible body; no accepted role."""
    def __init__(self,proof):
        self.proof=proof
        super().__init__('closed native response violates the bound body contract')


class PendingCleanupError(DockerRoleError):
    """Existing execution cannot yet be proven stopped; never seal its cost."""


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
        self.gemini_executable_sha256=policy['gemini_executable_sha256']
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
        if digest(_read(self.gemini_executable,536870912)) != self.gemini_executable_sha256:
            raise DockerRoleError('pinned Gemini executable changed before preparation')
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
            self._validate_launch(folder,plan,job_id,role,request)
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
        args=self._launch_argv(folder,role,request,label,nonce)
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

    def _launch_argv(self,folder,role,request,label,nonce):
        inp=folder/'input';name='specorganon-role-'+label
        image=self.images['test' if role=='test' else 'native']
        provider,model=self.routes[role] if role!='test' else (None,None)
        args = ['create', '--name', name, '--label', 'specorganon.run=' + label,
                '--label', 'specorganon.execution_nonce=' + nonce, '--read-only', '--cap-drop=ALL',
                '--security-opt', 'no-new-privileges', '--memory', '1g', '--cpus', '2', '--pids-limit', '128',
                '--tmpfs', '/tmp:rw,nosuid,size=256m', '--mount', f'type=bind,src={inp},dst=/input,readonly',
                '--mount', f'type=bind,src={folder / "output"},dst=/output', '-e', 'TMPDIR=/output']
        if role == 'test':
            args += ['--network', 'none', '-e', 'HOME=/output', '-w', '/input/delivery', '--entrypoint', '', image, *request['argv']]
        else:
            if self.seccomp: args += ['--security-opt', 'seccomp=' + str(inp / 'seccomp.json')]
            if provider == 'codex': args += ['--mount', f'type=volume,src={self.volume},dst=/home/codex/.codex',
                                            '-e','HOME=/home/codex','-e','CODEX_HOME=/home/codex/.codex']
            else:
                args += ['--mount', f'type=bind,src={self.gemini_profile},dst=/home/stev/.gemini',
                         '--mount', f'type=bind,src={self.gemini_executable},dst=/usr/local/bin/agy,readonly', '-e', 'HOME=/home/stev']
            args += ['-e', 'OPENAI_API_KEY=', '-e', 'PYTHONPATH=/input/library', '-e', 'SPECORGANON_ROLE_IMAGE_ID=' + image,
                     '-w', '/input', '--entrypoint', '/opt/specorganon/.venv/bin/python', image,
                     '/input/bridge.py', '--provider', provider, '--model', model, '--request', '/input/request.json', '--output-dir', '/output']
            if provider == 'gemini':
                args += ['--expected-executable-sha256',self.gemini_executable_sha256]
            if provider == 'codex':
                args += ['--model-catalog', '/input/public-models.json',
                         '--codex-reasoning-effort', self.codex_reasoning_effort]
        return args

    def _validate_launch(self,folder,plan,job_id,role,request):
        label=digest(canonical({'root':str(self.root),'job_id':job_id}))[:24]
        provider,model=self.routes[role] if role!='test' else (None,None)
        if (type(plan.get('schema')) is not int or plan['schema']!=2
                or plan.get('job_id')!=job_id or plan.get('role')!=role
                or plan.get('label')!=label or plan.get('name')!='specorganon-role-'+label
                or plan.get('provider')!=provider or plan.get('model')!=model
                or plan.get('image_id')!=self.images['test' if role=='test' else 'native']
                or plan.get('request_sha256')!=digest(canonical(request))
                or plan.get('codex_reasoning_effort')!=(self.codex_reasoning_effort if provider=='codex' else None)
                or type(plan.get('execution_nonce')) is not str
                or re.fullmatch(r'[0-9a-f]{32}',plan['execution_nonce']) is None
                or canonical(plan.get('create_argv'))!=canonical(self._launch_argv(folder,role,request,label,plan['execution_nonce']))):
            raise DockerRoleError('launch argv/environment/source policy diverged')

    def _inspect(self, plan):
        target=plan.get('container_id') or plan['name']
        try:result = self._cli(['inspect', target], allow_failure=True)
        except DockerControlDeadlineError as exc:
            raise PendingCleanupError('Docker inspection deadline cannot establish the owned execution state') from exc
        if result.returncode:
            error=result.stderr.decode(errors='replace').strip()
            if error in ('Error: No such object: '+target, 'error: no such object: '+target,
                         'Error response from daemon: No such container: '+target):return None
            raise PendingCleanupError('Docker inspection cannot establish the owned execution state')
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
        if role!='test' and digest(_read(self.gemini_executable,536870912))!=self.gemini_executable_sha256:
            raise DockerRoleError('pinned Gemini executable changed before dispatch')
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
        try:return self._reconcile_observed(job_id)
        except (DockerRoleError,UncertainJob) as exc:
            raise PendingCleanupError('owned execution stop is not confirmed; retain its reservation') from exc

    def _reconcile_observed(self, job_id):
        folder = self.root / 'jobs' / job_id; plan = _json(folder / 'launch.json'); value = self._inspect(plan)
        if value is not None and plan.get('container_id') is not None and value['Id']!=plan['container_id']:
            raise UncertainJob('owned name no longer identifies the recorded container; never kill replacement')
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
                if receipt['exit_code']==2 and not receipt['timed_out'] and not receipt['truncated_streams']:
                    try:proof=self.recover_response_failure(job_id,role,request)
                    except ValueError:proof=None
                    if proof is not None:raise ClosedResponseContractError(proof)
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

    def verify_role(self, packet, job_id, role, request):
        """Verify one already closed native role; never call/start/reconcile it.

        Trusted host/daemon records prove this supplied packet's provenance,
        not semantic truth, identity authentication or reviewer independence.
        Separate invocations/purposes must be enforced by the caller's history.
        """
        return self._verify_role_record(packet,job_id,role,request,failed_body=False)

    def _verify_role_record(self,packet,job_id,role,request,*,failed_body):
        expected_exit=2 if failed_body else 0
        provenance='closed_native_invalid_response' if failed_body else 'native'
        if type(role) is not str or role not in ('author','review') or type(job_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',job_id) is None:
            raise DockerRoleError('invalid role verification target')
        if type(packet) is not dict or packet.get('provenance') != provenance:
            raise DockerRoleError('native role provenance required')
        sources=self._bound_native_source_bytes()
        folder=self.root/'jobs'/job_id
        plan=_json(folder/'launch.json')
        provider,model=self.routes[role]
        self._validate_launch(folder,plan,job_id,role,request)
        if (plan['role'] != role or plan['request_sha256'] != digest(canonical(request))
                or plan['provider'] != provider or plan['model'] != model
                or plan['image_id'] != self.images['native']
                or self._inventory(folder/'input') != plan['input_manifest']):
            raise DockerRoleError('closed role request/source/route/image diverged')
        if (_read(folder/'input/request.json') != canonical(request)
                or any(_read(folder/'input'/('bridge.py' if name.startswith('scripts/')
                    else 'library/specorganon/'+Path(name).name)) != raw for name,raw in sources.items())):
            raise DockerRoleError('closed role prepared request/source differs from bound bytes')
        if (plan['container_id'] is None or _json(folder/'create-attempt.json') != self._creation_attempt(plan)):
            raise DockerRoleError('closed role lacks exact recorded creation intent')
        recovery=folder/'control-recovery.json';expected=plan.get('control_recovery_sha256')
        if (recovery.exists() != (expected is not None) or recovery.exists() and
                (digest(_read(recovery)) != expected or _json(recovery) != self._recovery_observation(plan,plan['container_id']))):
            raise DockerRoleError('closed role recovery history diverged')
        path=self.store.root/job_id
        receipt=_json(path/'receipt.json');self.store._validate_receipt(path,job_id,receipt)
        admitted=_json(path/'request.json')
        metadata={'role':role,'provider':provider,'model':model,'image_id':plan['image_id'],
                  'container_id':plan['container_id'],'input_manifest':plan['input_manifest']}
        if (canonical(admitted['request']) != canonical(request) or canonical(receipt['metadata']) != canonical(metadata)
                or canonical(admitted['metadata']) != canonical(metadata) or digest(canonical(admitted)) != receipt['request_sha256']
                or receipt['argv'] != ['/usr/bin/docker','start','--attach',plan['container_id']]
                or admitted['argv'] != receipt['argv'] or admitted['cwd'] != str(self.root)
                or receipt['cwd'] != str(self.root) or receipt['exit_code'] != expected_exit
                or receipt['timed_out'] or receipt['truncated_streams']):
            raise DockerRoleError('closed role measured admission/receipt diverged or failed')
        for name in ('stdout','stderr'):
            raw=_read(path/(name+'.bin'))
            if digest(raw) != receipt[name+'_sha256'] or len(raw) != receipt[name+'_bytes']:
                raise DockerRoleError('closed role measured stream changed')
        terminal=_json(folder/'terminal-container.json')
        if canonical(terminal) != canonical({'id':plan['container_id'],'exit_code':expected_exit,'image_id':plan['image_id'],'oom_killed':False}):
            raise DockerRoleError('closed role terminal container diverged or failed')
        if failed_body:
            if _read(path/'stdout.bin')!=b'':raise DockerRoleError('failed response bridge must not emit an accepted packet')
            actual=self._failed_response_packet(folder,provider,model,request)
        else:actual=strict_json_loads(_read(path/'stdout.bin').decode())
        if (type(actual) is not dict or type(actual.get('schema')) is not int or actual['schema'] != 1
                or type(actual.get('native_exit_code')) is not int):
            raise DockerRoleError('invalid exact native bridge packet schema')
        expected_packet={**actual,'actor':('agent:' if role=='author' else 'reviewer:')+provider+'-isolated-'+role,
                         'receipt_ref':str(path/'receipt.json'),'provenance':provenance}
        if (canonical(packet) != canonical(expected_packet) or actual.get('request_sha256') != plan['request_sha256']
                or actual.get('provider') != provider or actual.get('model') != model
                or actual.get('native_exit_code') != 0):
            raise DockerRoleError('supplied role packet differs from actual closed stdout')
        self._verify_invocation(folder,actual,request,provider,model,failed_body=failed_body)
        return True

    def _failed_response_packet(self,folder,provider,model,request):
        from .native_transcript import parse_native,parse_gemini_stream
        _,receipt,streams=self._closed_native_record(folder/'output/native','call')
        reconnections=[]
        body,usage=(parse_gemini_stream(streams['stdout'].decode()) if provider=='gemini' else
                    parse_native(provider,streams['stdout'].decode(),diagnostics=reconnections))
        return {'schema':1,'provider':provider,'model':model,'request_sha256':digest(canonical(request)),
                'native_exit_code':0,'invocation_metadata':receipt['metadata'],'result':body,
                'usage_reported':usage,'native_reconnections':reconnections}

    def recover_response_failure(self,job_id,role,request):
        path=self.store.root/job_id
        if not (path/'receipt.json').exists() or _json(path/'receipt.json')['exit_code']!=2:return None
        provider,model=self.routes[role]
        packet=self._failed_response_packet(self.root/'jobs'/job_id,provider,model,request)
        proof={**packet,'actor':('agent:' if role=='author' else 'reviewer:')+provider+'-isolated-'+role,
               'receipt_ref':str(path/'receipt.json'),'provenance':'closed_native_invalid_response'}
        self._verify_role_record(proof,job_id,role,request,failed_body=True)
        return proof

    def verify_response_failure(self,proof,job_id,role,request):
        return self._verify_role_record(proof,job_id,role,request,failed_body=True)

    @staticmethod
    def _closed_native_record(root,job_id):
        """Pure host verification of the instrumented bridge's inner journal."""
        root=_safe(root);_json(root/'policy.json')
        store=JobStore.__new__(JobStore);store.root=root
        store._root_fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            path=root/job_id;receipt=store._json(path/'receipt.json')
            store._validate_receipt(path,job_id,receipt)
            envelope=store._json(path/'request.json')
            if (digest(canonical(envelope))!=receipt['request_sha256']
                    or canonical(envelope['metadata'])!=canonical(receipt['metadata'])
                    or canonical(envelope['argv'])!=canonical(receipt['argv'])
                    or envelope['cwd']!=receipt['cwd'] or receipt['exit_code']!=0
                    or receipt['timed_out'] or receipt['truncated_streams'] or receipt['stdin_complete'] is not True):
                raise DockerRoleError('native inner admission/closing record diverged or failed')
            for stream in ('stdout','stderr'):
                raw=store._read(path/(stream+'.bin'))
                if digest(raw)!=receipt[stream+'_sha256'] or len(raw)!=receipt[stream+'_bytes']:
                    raise DockerRoleError('native inner measured stream changed')
            return envelope,receipt,{name:store._read(path/(name+'.bin')) for name in ('stdout','stderr')}
        finally:os.close(store._root_fd);store._root_fd=None

    def _verify_invocation(self,folder,actual,request,provider,model,*,failed_body=False):
        from .native_response_contract import (render_prompt,response_contract_from_request,native_command,
                                              role_model_catalog,CODEX_TEXT_ONLY_DISABLED)
        meta=actual.get('invocation_metadata')
        _,prompt=render_prompt(canonical(request));output=folder/'output'
        if (type(meta) is not dict or type(meta.get('schema')) is not int or meta['schema']!=1
                or meta.get('image_id')!=self.images['native']
                or meta.get('response_schema_sha256')!=digest(canonical(response_contract_from_request(request)))
                or meta.get('response_schema_scope')!='Prompt guidance and strict local validation only; no provider enforcement claim'
                or type(meta.get('executable_sha256')) is not str
                or re.fullmatch(r'[0-9a-f]{64}',meta['executable_sha256']) is None
                or meta.get('known_configuration_sha256') is not None and
                   re.fullmatch(r'[0-9a-f]{64}',str(meta['known_configuration_sha256'])) is None
                or meta.get('other_effective_configuration')!='unknown; trusted launcher/profile boundary'
                or meta.get('known_configuration_path')!=('/home/codex/.codex/config.toml' if provider=='codex'
                    else '/home/stev/.gemini/settings.json')
                or _read(output/'role-response-schema.json')!=canonical(response_contract_from_request(request))):
            raise DockerRoleError('native invocation identity/schema metadata differs from launch pins')
        envelope,receipt,streams=self._closed_native_record(output/'native','call')
        if (canonical(meta)!=canonical(receipt['metadata']) or envelope['request']!={'provider':provider,'model':model}
                or envelope['cwd']!='/input' or envelope['timeout_seconds']!=180):
            raise DockerRoleError('native invocation packet differs from actual measured inner call')
        names=[];catalog=None;effort=None
        if provider=='codex':
            if type(meta.get('executable_path')) is not str or not meta['executable_path'].startswith('/usr/local/'):
                raise DockerRoleError('native Codex executable must resolve inside the pinned image')
            public=_read(folder/'input/public-models.json')
            if digest(public)!=self.launch_input_sha256['public-models.json']:
                raise DockerRoleError('prepared public catalog differs from frozen launch input')
            projected=canonical(role_model_catalog(strict_json_loads(public.decode()),model))
            catalog='/output/runtime-model-catalog.json';effort=self.codex_reasoning_effort
            if (meta.get('public_model_catalog_sha256')!=digest(public)
                    or meta.get('runtime_model_catalog_sha256')!=digest(projected)
                    or _read(output/'runtime-model-catalog.json')!=projected
                    or meta.get('requested_reasoning_effort')!=effort
                    or meta.get('effective_remote_reasoning_effort')!='not observed'
                    or meta.get('tool_surface_override')!='direct; no shell, patch, search or experimental tools'
                    or meta.get('effective_features',{}).get('disabled_features')!=CODEX_TEXT_ONLY_DISABLED):
                raise DockerRoleError('native Codex catalog/effort/tool surface differs from launch pins')
            for arg in envelope['argv']:
                if arg.startswith('mcp_servers.') and arg.endswith('.enabled=false'):
                    names.append(arg[len('mcp_servers.'):-len('.enabled=false')])
            checked,check_receipt,check_streams=self._closed_native_record(output/'native','configuration-check')
            from .native_transcript import validate_codex_features
            base_meta={k:v for k,v in meta.items() if k!='effective_features'}
            expected_prefix=[envelope['argv'][0]]
            for i,arg in enumerate(envelope['argv'][:-1]):
                if arg in ('-c','--disable'):expected_prefix += [arg,envelope['argv'][i+1]]
            if (checked['argv']!=expected_prefix+['features','list'] or checked['cwd']!='/input'
                    or checked['request']!={'purpose':'native feature restriction check, no model call'}
                    or canonical(check_receipt['metadata'])!=canonical(base_meta)
                    or checked['environment_sha256']!=envelope['environment_sha256']
                    or checked['timeout_seconds']!=10 or checked['stdin_sha256'] is not None
                    or check_receipt['stdin_bytes_expected']!=0
                    or canonical(validate_codex_features(check_streams['stdout'].decode()))!=canonical(meta['effective_features'])):
                raise DockerRoleError('native effective configuration preflight differs from actual command')
        elif (meta.get('executable_path')!='/usr/local/bin/agy'
                or meta['executable_sha256']!=self.gemini_executable_sha256):
            raise DockerRoleError('native Gemini executable differs from frozen launcher pin')
        expected=native_command(provider,model,model_catalog=catalog,reasoning_effort=effort,mcp_names=names)
        payload=(canonical({'event':'user','message':{'role':'user','content':[{'type':'text','text':prompt}]}})+b'\n') if provider=='gemini' else prompt.encode()
        if (envelope['argv']!=expected or envelope.get('stdin_sha256')!=digest(payload)
                or receipt['stdin_bytes_sent']!=len(payload) or receipt['stdin_bytes_expected']!=len(payload)):
            raise DockerRoleError('native argv or full transmitted prompt differs from bound request')
        from .native_transcript import parse_native,parse_gemini_stream,validate_result
        from .native_response_contract import author_format_from_request,validate_response_schema
        reconnections=[]
        body,usage=(parse_gemini_stream(streams['stdout'].decode()) if provider=='gemini' else
                    parse_native(provider,streams['stdout'].decode(),diagnostics=reconnections))
        if (canonical(body)!=canonical(actual.get('result')) or canonical(usage)!=canonical(actual.get('usage_reported'))
                or canonical(reconnections)!=canonical(actual.get('native_reconnections'))):
            raise DockerRoleError('native packet body/usage/reconnections differ from actual transcript')
        try:
            validate_result(body,request['role'],author_format=author_format_from_request(request))
            validate_response_schema(body,response_contract_from_request(request))
        except ValueError:
            if not failed_body:raise
        else:
            if failed_body:raise DockerRoleError('valid body cannot be promoted as a methodological response failure')

    def reconcile_pending(self,job_id,role,request):
        """Stop only the exact owned pending container; never prepare or start."""
        if type(job_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',job_id) is None:
            raise DockerRoleError('invalid pending reconciliation target')
        folder=self.root/'jobs'/job_id
        if not (folder/'launch.json').exists():return False
        if role=='test':request={'schema':1,'argv':request['argv'],'delivery_tree_sha256':digest(canonical(request['files']))}
        try:
            plan=_json(folder/'launch.json');self._validate_launch(folder,plan,job_id,role,request)
            if not (folder/'create-attempt.json').exists():return False
            if _json(folder/'create-attempt.json')!=self._creation_attempt(plan):
                raise DockerRoleError('pending cleanup creation intent diverged')
            self.reconcile(job_id)
        except (ValueError,OSError) as exc:
            raise PendingCleanupError('owned pending execution cleanup is not confirmed; retain exact reservation') from exc
        return True

    def recover_role(self,job_id,role,request):
        """Read only a fully closed role, without dispatch or Docker control."""
        path=self.store.root/job_id
        if not (path/'receipt.json').exists():return None
        if not (self.root/'jobs'/job_id/'terminal-container.json').exists():return None
        if _json(path/'receipt.json')['exit_code']==2:
            proof=self.recover_response_failure(job_id,role,request)
            if proof is not None:raise ClosedResponseContractError(proof)
        actual=strict_json_loads(_read(path/'stdout.bin').decode())
        if type(actual) is not dict:raise DockerRoleError('invalid closed bridge stdout')
        provider,_=self.routes[role]
        packet={**actual,'actor':('agent:' if role=='author' else 'reviewer:')+provider+'-isolated-'+role,
                'receipt_ref':str(path/'receipt.json'),'provenance':'native'}
        self.verify_role(packet,job_id,role,request)
        return packet

    def recover_test(self,job_id,argv,files):
        """Read a fully closed measurement, without dispatch or Docker control."""
        folder=self.root/'jobs'/job_id
        if not (self.store.root/job_id/'receipt.json').exists() or not (folder/'terminal-container.json').exists():return None
        return self._closed_test_result({'argv':argv,'test_job_ref':str(self.store.root/job_id/'receipt.json')},
                                        files,require_passed=False)

    def verify_test(self, data, files, *, require_passed=True, require_current=True):
        self._closed_test_result(data,files,require_passed=require_passed,require_current=require_current)
        return True

    def _closed_test_result(self,data,files,*,require_passed=True,require_current=True):
        path=_safe(data['test_job_ref'])
        if path.parent.parent!=self.store.root or path.name!='receipt.json':
            raise DockerRoleError('test receipt lies outside this private journal')
        job_id=path.parent.name;folder=self.root/'jobs'/job_id
        receipt=_json(path);self.store._validate_receipt(path.parent,job_id,receipt)
        admitted=_json(path.parent/'request.json');request=admitted['request']
        plan=_json(folder/'launch.json');self._validate_launch(folder,plan,job_id,'test',request)
        terminal=_json(folder/'terminal-container.json')
        metadata={'role':'test','provider':None,'model':None,'image_id':plan['image_id'],
                  'container_id':plan['container_id'],'input_manifest':plan['input_manifest']}
        if (digest(canonical(admitted))!=receipt['request_sha256']
                or canonical(admitted['metadata'])!=canonical(metadata) or canonical(receipt['metadata'])!=canonical(metadata)
                or receipt['argv']!=['/usr/bin/docker','start','--attach',plan['container_id']]
                or admitted['argv']!=receipt['argv'] or admitted['cwd']!=str(self.root) or receipt['cwd']!=str(self.root)
                or _read(folder/'input/request.json')!=canonical(request)
                or self._inventory(folder/'input')!=plan['input_manifest']
                or _json(folder/'create-attempt.json')!=self._creation_attempt(plan)
                or type(terminal.get('exit_code')) is not int or terminal.get('oom_killed') is not False
                or set(terminal)!={'id','exit_code','image_id','oom_killed'}
                or terminal['id']!=plan['container_id'] or terminal['image_id']!=plan['image_id']):
            raise DockerRoleError('test measured admission/launch/terminal diverged')
        original={str(p.relative_to(folder/'input/delivery')):_read(p).decode()
                  for p in sorted((folder/'input/delivery').rglob('*')) if p.is_file()}
        if digest(canonical(original))!=request['delivery_tree_sha256']:
            raise DockerRoleError('original test delivery differs from admitted fingerprint')
        expected={**receipt,'subject_argv':request['argv'],'attachment_exit_code':receipt['exit_code'],
            'exit_code':terminal['exit_code'],'test_job_ref':str(path),
            'delivery_tree_sha256':request['delivery_tree_sha256'],'image_id':plan['image_id'],
            'container_id':plan['container_id'],'provenance':'actual_isolated_container',
            'passed':receipt['exit_code']==0 and terminal['exit_code']==0
                     and not receipt['timed_out'] and not receipt['truncated_streams']}
        actual=_json(folder/'measured-test.json') if (folder/'measured-test.json').exists() else None
        if (actual is not None and canonical(actual)!=canonical(expected)
                or (require_current and request['delivery_tree_sha256']!=digest(canonical(files)))
                or data.get('delivery_tree_sha256',request['delivery_tree_sha256'])!=request['delivery_tree_sha256']
                or request['argv']!=data['argv'] or (require_passed and expected['passed'] is not True)):
            raise DockerRoleError('test receipt/current delivery diverged or fabricated outcome')
        for name in ('stdout','stderr'):
            raw=_read(path.parent/(name+'.bin'))
            if digest(raw)!=receipt[name+'_sha256'] or len(raw)!=receipt[name+'_bytes']:
                raise DockerRoleError('test measured stream changed')
        return expected
