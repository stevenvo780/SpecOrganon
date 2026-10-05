"""Uncredentialed LotLedger subjects; expected outputs stay on the trusted host."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re

from specorganon.docker_roles import DockerRoles
from specorganon.role_jobs import JobStore, UncertainJob, _json, _write, _safe, canonical, digest
from specorganon.software_controller import safe_file, encoded_contribution
from .reserved import judge, recipes


class SubjectError(ValueError):
    pass


class Subjects:
    def __init__(self, root, image):
        self.root = _safe(root)
        self.image = DockerRoles._image(image)
        self.matrix = {r['id']: r for r in recipes()}
        policy = {'schema': 1, 'image': self.image, 'matrix_sha256': digest(canonical(list(self.matrix.values()))),
                  'source_sha256': digest(Path(__file__).read_bytes()), 'seconds': 3, 'attach_seconds': 10,
                  'cpus': 2, 'memory': '1g', 'pids': 128, 'stream_bytes': 2097152, 'max_subjects': len(self.matrix)}
        path = self.root / 'policy.json'
        if path.exists() and _json(path) != policy: raise SubjectError('subject policy changed')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.stat().st_uid != os.geteuid() or self.root.stat().st_mode & 0o022:
            raise SubjectError('private owned subject journal required')
        self.store = JobStore(self.root / 'journal', max_jobs=len(self.matrix), max_elapsed_seconds=6000)
        if not path.exists(): _write(path, policy)

    @contextmanager
    def lock(self):
        fd = os.open(self.root / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally: os.close(fd)

    def inspect(self, plan):
        result = DockerRoles._cli(['inspect', plan['name']], allow_failure=True)
        if result.returncode: return None
        value = __import__('json').loads(result.stdout)[0]
        if value['Image'] != self.image or value['Config']['Labels'].get('specorganon.lotledger') != plan['label']:
            raise SubjectError('owned subject identity diverged')
        return value

    def reconcile(self, folder, plan):
        value = self.inspect(plan)
        if value and value['State']['Running']:
            DockerRoles._cli(['kill', value['Id']], allow_failure=True)
            value = self.inspect(plan)
            if value and value['State']['Running']: raise SubjectError('owned subject still running')
        _write(folder / 'uncertain.json', {'status': 'inconclusive', 'handle_missing': value is None, 'restarted': False})

    def run(self, identity, recipe, files):
        if (type(identity) is not str or identity not in self.matrix or recipe != self.matrix[identity]
                or type(files) is not dict or 'lotledger.py' not in files
                or any(type(k) is not str or type(v) is not str for k, v in files.items())):
            raise SubjectError('unregistered recipe or invalid delivery')
        if encoded_contribution(files) > 20000: raise SubjectError('delivery envelope exceeded')
        for name in files: safe_file(name)
        job_id = digest(canonical({'namespace': 'lotledger.subject.v1', 'id': identity}))
        binding = {'logical_id': identity, 'opaque_id': job_id, 'recipe_sha256': digest(canonical(recipe)),
                   'delivery_sha256': digest(canonical(files))}
        with self.lock():
            folder = self.root / 'invocations' / job_id
            if folder.exists():
                if not (folder / 'plan.json').exists(): raise UncertainJob('subject preparation interrupted')
                plan = _json(folder / 'plan.json')
                if plan['binding'] != binding: raise SubjectError('closed subject inputs changed')
            else:
                folder.mkdir(parents=True, mode=0o700)
                delivery = folder / 'input' / 'delivery'; delivery.mkdir(parents=True, mode=0o700)
                for name, content in files.items():
                    path = delivery / name; path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    path.write_text(content, encoding='utf-8')
                label = digest(canonical({'root': str(self.root), 'job': job_id}))
                name = 'specorganon-lot-' + label
                command = ['/usr/bin/timeout', '--signal=KILL', '3s', '/opt/specorganon/venv/bin/python',
                           '-E', '-s', '-B', '/input/delivery/lotledger.py', *recipe['argv']]
                args = ['create', '--name', name, '--label', 'specorganon.lotledger=' + label,
                        '--interactive', '--read-only', '--network', 'none', '--cap-drop=ALL',
                        '--security-opt', 'no-new-privileges', '--user', '1000:1000', '--memory', '1g',
                        '--cpus', '2', '--pids-limit', '128', '--tmpfs', '/tmp:rw,nosuid,size=64m',
                        '-e', 'HOME=/tmp', '-e', 'TMPDIR=/tmp', '--mount',
                        f'type=bind,src={delivery},dst=/input/delivery,readonly',
                        '-w', '/input/delivery', '--entrypoint', '', self.image, *command]
                plan = {'schema': 1, 'binding': binding, 'name': name, 'label': label,
                        'create_argv': args, 'subject_command': command, 'container_id': None,
                        'inventory': DockerRoles._inventory(delivery)}
                _write(folder / 'plan.json', plan)
            delivery = folder / 'input' / 'delivery'
            if DockerRoles._inventory(delivery) != {k: digest(v.encode()) for k, v in files.items()}:
                raise SubjectError('prepared delivery bytes diverged')
            value = self.inspect(plan)
            if plan['container_id'] is None:
                if value is None:
                    handle = DockerRoles._cli(plan['create_argv']).stdout.decode().strip()
                    if not re.fullmatch('[0-9a-f]{64}', handle): raise SubjectError('invalid created handle')
                    plan['container_id'] = handle
                else: plan['container_id'] = value['Id']
                _write(folder / 'plan.json', plan); value = self.inspect(plan)
            if value is None or value['Id'] != plan['container_id']:
                raise UncertainJob('owned handle missing; never recreate')
            if value['Config']['Cmd'] != plan['subject_command'] or value['Config']['Entrypoint'] not in (None, []):
                raise SubjectError('subject command diverged')
            closed = (self.store.root / job_id / 'receipt.json').exists()
            started = (self.store.root / job_id / 'started.json').exists()
            if value['State']['Status'] != 'created' and not closed and not started:
                self.reconcile(folder, plan); raise UncertainJob('subject previously started without journal')
            try:
                job = self.store.execute(job_id, ['/usr/bin/docker', 'start', '--attach', '--interactive', plan['container_id']],
                    binding, cwd=self.root, timeout_seconds=10, metadata={'image': self.image, 'container': plan['container_id']},
                    cancel_argv=['/usr/bin/docker', 'kill', plan['container_id']], stdin_bytes=bytes.fromhex(recipe['stdin_hex']))
            except UncertainJob:
                self.reconcile(folder, plan); raise
            value = self.inspect(plan)
            if value is None or value['State']['Running']:
                self.reconcile(folder, plan); raise UncertainJob('subject closure unknown')
            if DockerRoles._inventory(delivery) != plan['inventory']: raise SubjectError('delivery changed during subject')
            receipt = job['receipt']; code = value['State']['ExitCode']
            if code != receipt['exit_code'] and not (receipt['timed_out'] or receipt['truncated_streams']):
                raise SubjectError('attachment and subject exit diverged')
            result = {'exit_code': code, 'stdout': job['stdout'], 'stderr': job['stderr'],
                      'timed_out': code == 137 or receipt['timed_out'], 'truncated_streams': receipt['truncated_streams'],
                      'infrastructure_error': 'attachment timeout' if receipt['timed_out'] else None}
            verdict = judge(recipe, result)
            public = {'id': identity, 'public': recipe['public'], **verdict, 'receipt_ref': str(self.store.root / job_id / 'receipt.json'),
                      'exit_code': code, 'timed_out': result['timed_out'], 'oom_killed': value['State']['OOMKilled'],
                      'stdout_sha256': digest(job['stdout']), 'stderr_sha256': digest(job['stderr']),
                      'duration_seconds': receipt['duration_seconds']}
            _write(folder / 'verdict.json', public)
            return public
