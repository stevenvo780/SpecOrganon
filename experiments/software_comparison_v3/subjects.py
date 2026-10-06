"""Uncredentialed prospective v3 subjects; expected outputs stay on the trusted host."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re

from specorganon.docker_roles import DockerRoles
from specorganon.role_jobs import JobStore, UncertainJob, _json, _read, _write, _safe, canonical, digest
from specorganon.software_controller import safe_file, encoded_contribution
from . import reserved as _oracles
from .reserved import judge, recipes, TASK_FILES


class SubjectError(ValueError):
    pass


HELD_OPEN_WRAPPER = '''import subprocess,sys,os,json,hashlib
trace='/observer/stdin.trace'
calls='read,readv,pread64,preadv,preadv2,splice,vmsplice,sendfile,copy_file_range,recvfrom,recvmsg,recvmmsg,poll,ppoll,select,pselect6,mmap'
p=subprocess.Popen(['/usr/bin/strace','-f','-qq','-yy','-s','64','-o',trace,'-e','trace='+calls,*sys.argv[1:]],stdin=subprocess.PIPE)
inode=os.fstat(p.stdin.fileno()).st_ino
try:
    code=p.wait(timeout=2.5)
except subprocess.TimeoutExpired:
    p.kill()
    p.wait()
    code=124
finally:
    p.stdin.close()
try:
    with open(trace,'rb') as stream: raw=stream.read(2097153)
    if len(raw)>2097152: raise ValueError('trace cap')
    marker=('pipe:['+str(inode)+']').encode()
    violations=[line.decode('utf-8','strict') for line in raw.splitlines() if marker in line]
    if violations and code!=124: code=125
    report={'schema':1,'stdin_pipe_inode':inode,'observed_stdin_syscalls':violations[:64],'trace_sha256':hashlib.sha256(raw).hexdigest(),'trace_bytes':len(raw),'exit_code':code,'scope':'listed syscalls with stdin pipe annotation; finite observation'}
    with open('/observer/stdin-observer.json','w') as stream: json.dump(report,stream)
except (OSError,ValueError,UnicodeError):
    code=126
sys.exit(code)
'''


def subject_command(recipe):
    """Fixed argv; one registered probe keeps child stdin open with no data/EOF."""
    python='/opt/specorganon/venv/bin/python'
    child=[python,'-E','-s','-B','/input/delivery/' + TASK_FILES[recipe['task']],*recipe['argv']]
    if recipe.get('stdin_mode') == 'held_open':
        child=[python,'-E','-s','-B','-c',HELD_OPEN_WRAPPER,*child]
    return ['/usr/bin/timeout','--signal=KILL','3s',*child]


class Subjects:
    def __init__(self, root, image, task):
        self.root = _safe(root)
        self.image = DockerRoles._image(image)
        self.filename = TASK_FILES[task]
        self.task = task
        self.matrix = {r['id']: r for r in recipes(task)}
        policy = {'schema': 1, 'task': task, 'image': self.image, 'matrix_sha256': digest(canonical(list(self.matrix.values()))),
                  'source_sha256': digest(Path(__file__).read_bytes()), 'seconds': 3, 'attach_seconds': 10,
                  'oracle_source_sha256': digest(Path(_oracles.__file__).read_bytes()),
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
        if value['Image'] != self.image or value['Config']['Labels'].get('specorganon.comparison-v3') != plan['label']:
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
                or type(files) is not dict or self.filename not in files
                or any(type(k) is not str or type(v) is not str for k, v in files.items())):
            raise SubjectError('unregistered recipe or invalid delivery')
        if encoded_contribution(files) > 20000: raise SubjectError('delivery envelope exceeded')
        for name in files: safe_file(name)
        job_id = digest(canonical({'namespace': 'comparison.v3.subject.v1', 'id': identity}))
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
                name = 'specorganon-v3-' + label
                command = subject_command(recipe)
                args = ['create', '--name', name, '--label', 'specorganon.comparison-v3=' + label,
                        '--interactive', '--read-only', '--network', 'none', '--cap-drop=ALL',
                        '--security-opt', 'no-new-privileges', '--user', '1000:1000', '--memory', '1g',
                        '--cpus', '2', '--pids-limit', '128', '--tmpfs', '/tmp:rw,nosuid,size=64m',
                        '-e', 'HOME=/tmp', '-e', 'TMPDIR=/tmp', '--mount',
                        f'type=bind,src={delivery},dst=/input/delivery,readonly',
                        '-w', '/input/delivery', '--entrypoint', '', self.image, *command]
                if recipe.get('stdin_mode') == 'held_open':
                    observer=folder/'observer';observer.mkdir(mode=0o700)
                    args[1:1]=['--mount',f'type=bind,src={observer},dst=/observer']
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
                      'timed_out': code == 137 or (code == 124 and recipe.get('stdin_mode') == 'held_open') or receipt['timed_out'], 'truncated_streams': receipt['truncated_streams'],
                      'infrastructure_error': 'attachment timeout' if receipt['timed_out'] else None}
            verdict = judge(recipe, result)
            observer_ref=None;observer_sha=None
            if recipe.get('stdin_mode') == 'held_open':
                report=folder/'observer/stdin-observer.json'
                if report.exists():
                    # Observer output is private evidence, never authority for
                    # overriding the captured child/container status or streams.
                    observed=_json(report)
                    trace=folder/'observer/stdin.trace'
                    if (observed.get('schema')!=1 or observed.get('exit_code')!=code
                            or observed.get('trace_sha256')!=digest(_read(trace,2097152))):
                        raise SubjectError('closed observer trace/report diverged')
                    observer_ref=str(report);observer_sha=digest(canonical(observed))
                elif code==2:
                    raise UncertainJob('closed ordering probe lacks observer report; never replay execution')
            public = {'id': identity, 'public': recipe['public'], **verdict, 'receipt_ref': str(self.store.root / job_id / 'receipt.json'),
                      'exit_code': code, 'timed_out': result['timed_out'], 'oom_killed': value['State']['OOMKilled'],
                      'stdout_sha256': digest(job['stdout']), 'stderr_sha256': digest(job['stderr']),
                      'observer_ref':observer_ref,'observer_sha256':observer_sha,
                      'duration_seconds': receipt['duration_seconds']}
            _write(folder / 'verdict.json', public)
            return public
