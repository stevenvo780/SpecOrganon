"""Single-attempt offline D106 environment preparation; no source-row execution."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess
import time

ROOT = Path('/workspace/SpecOrganon')
DOSSIER = ROOT / 'experiments/development/citibike_raw_count_audit_2026-09-30'
STREAMS = DOSSIER / 'setup'
RUNTIME = Path('/tmp/specorganon-D106-raw-bdp0u2dw')
VENV = RUNTIME / 'venv'
UV = '/home/dev/.local/bin/uv'
BASE_PYTHON = '/workspace/SpecOrganon/.venv/bin/python'
CACHE = '/home/dev/.cache/uv'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TZ': 'UTC'}
GLOBAL = [UV, '--offline', '--no-config', '--no-python-downloads', '--cache-dir', CACHE]

MANIFEST_CODE = r'''
from pathlib import Path
import base64,hashlib,importlib.metadata as md,json,stat,sys
venv=Path(sys.prefix).resolve()
expected={'pyarrow':'21.0.0','tzdata':'2026.4'}
version=sys.version.split()[0]
if version!='3.11.15':raise RuntimeError('unexpected Python '+version)
installed={d.metadata['Name'].lower():d.version for d in md.distributions()}
if installed!=expected:raise RuntimeError('unexpected distributions '+repr(installed))
out={'schema':1,'venv':str(venv),'python':{'version':version,'executable':sys.executable,'base_prefix':sys.base_prefix},'distributions':{},'files':{},'symlinks':[],'excluded_pycache':[],'record_validation':{'matched':0,'unhashed_entries':0,'mismatched':0}}
for name,required_version in expected.items():
 d=md.distribution(name)
 if d.version!=required_version:raise RuntimeError('wrong version '+name)
 files=d.files
 if files is None:raise RuntimeError('missing RECORD file list for '+name)
 packagefiles=[];recordlisted=set();nonregular=[]
 for rel in files:
  p=Path(d.locate_file(rel)).absolute()
  if not p.is_relative_to(venv):raise RuntimeError('distribution path outside venv '+str(p))
  key=str(p.relative_to(venv));recordlisted.add(key)
  if '__pycache__' in p.parts or p.suffix=='.pyc':
   if p.exists():out['excluded_pycache'].append(key)
   continue
  s=p.lstat()
  if stat.S_ISLNK(s.st_mode):
   out['symlinks'].append({'path':key,'distribution':name,'target':p.readlink().as_posix()});continue
  if not stat.S_ISREG(s.st_mode):nonregular.append(key);continue
  if not p.resolve().is_relative_to(venv):raise RuntimeError('resolved path outside venv '+key)
  h=hashlib.sha256();size=0
  with p.open('rb') as f:
   for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk);size+=len(chunk)
  out['files'][key]={'bytes':size,'sha256':h.hexdigest()};packagefiles.append(key)
  if rel.hash:
   encoded=base64.urlsafe_b64encode(h.digest()).decode().rstrip('=')
   if rel.hash.mode!='sha256' or rel.hash.value!=encoded or (rel.size is not None and rel.size!=size):
    out['record_validation']['mismatched']+=1;raise RuntimeError('wheel RECORD differs '+key)
   out['record_validation']['matched']+=1
  else:out['record_validation']['unhashed_entries']+=1
 # Audit ownership completeness across the package and its dist-info directories.
 roots={Path(d.locate_file(name)).absolute()}
 roots.update(Path(d.locate_file(rel)).absolute().parent for rel in files if str(rel).endswith('.dist-info/METADATA'))
 unlisted=[]
 for package_root in roots:
  for p in package_root.rglob('*'):
   if '__pycache__' in p.parts or p.suffix=='.pyc':continue
   if p.is_symlink():
    key=str(p.relative_to(venv))
    if not any(x['path']==key for x in out['symlinks']):out['symlinks'].append({'path':key,'distribution':name,'target':p.readlink().as_posix()})
    continue
   if p.is_file() and str(p.relative_to(venv)) not in recordlisted:unlisted.append(str(p.relative_to(venv)))
 if unlisted:raise RuntimeError('regular package files absent from RECORD '+repr(unlisted))
 out['distributions'][name]={'version':d.version,'metadata_origin':str(d._path),'package_origin':str(d.locate_file(name)),'installer':(d.read_text('INSTALLER') or '').strip(),'regular_file_count':len(packagefiles),'regular_file_bytes':sum(out['files'][x]['bytes'] for x in packagefiles),'nonregular_entries':nonregular,'unlisted_regular_files':unlisted}
out['file_count']=len(out['files']);out['regular_file_bytes']=sum(x['bytes'] for x in out['files'].values())
print(json.dumps(out,sort_keys=True,ensure_ascii=False,allow_nan=False))
'''


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


setup = {'schema': 1, 'study_id': 'D106', 'started_at_utc': stamp(),
         'runtime': str(RUNTIME), 'venv': str(VENV),
         'plan_sha256': digest(DOSSIER / 'plan.json'),
         'setup_script_sha256': digest(__file__),
         'environment_allowlist': ENV, 'home_inherited': False,
         'tool_paths': {'uv': UV, 'base_python': BASE_PYTHON, 'cache': CACHE},
         'tool_hashes': {'uv': digest(UV), 'base_python_resolved': digest(Path(BASE_PYTHON).resolve())},
         'offline': True, 'config_disabled': True, 'keyring_disabled_for_install': True,
         'build_disabled_for_install': True, 'link_mode': 'copy',
         'retries': 0, 'downloads_requested': 0, 'auth_copied': False,
         'analyzer_executed': False, 'raw_rows_read': False,
         'toolkit_environments_modified': False, 'commands': [], 'status': 'running'}


def save():
    (DOSSIER / 'environment_setup.json').write_text(
        json.dumps(setup, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n')


def capture(name, argv):
    record = {'name': name, 'argv': argv, 'cwd': str(RUNTIME),
              'environment': ENV, 'started_at_utc': stamp()}
    started = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=RUNTIME, env=ENV, capture_output=True, timeout=60, check=False)
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code = exc.stdout or b'', exc.stderr or b'', None
        record['timeout_seconds'] = 60
        record['error'] = 'subprocess exceeded timeout; no retry'
    except OSError as exc:
        stdout, stderr, code = b'', b'', None
        record['error'] = str(exc)
    record.update({'finished_at_utc': stamp(), 'wall_seconds_local': time.monotonic() - started,
                   'exit_code': code, 'stdout': str(STREAMS / (name + '.stdout')),
                   'stderr': str(STREAMS / (name + '.stderr'))})
    for kind, content in [('stdout', stdout), ('stderr', stderr)]:
        path = Path(record[kind])
        with path.open('xb') as stream:
            stream.write(content)
        record[kind + '_bytes'] = len(content)
        record[kind + '_sha256'] = hashlib.sha256(content).hexdigest()
    with (STREAMS / (name + '.command.json')).open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    setup['commands'].append(record)
    save()
    if code != 0:
        raise RuntimeError('command failed: ' + name + ', exit=' + str(code))
    return stdout


try:
    if (DOSSIER / 'environment_setup.json').exists() or (DOSSIER / 'environment_manifest.json').exists():
        raise RuntimeError('owned output already exists; no overwrite or retry')
    if VENV.exists():
        raise RuntimeError('external venv already exists; no reuse or overwrite')
    RUNTIME.mkdir(parents=True, exist_ok=True)
    capture('01_uv_version', [UV, '--version'])
    capture('02_venv', GLOBAL + ['venv', '--python', BASE_PYTHON, str(VENV)])
    capture('03_install', GLOBAL + ['pip', 'install', '--python', str(VENV / 'bin/python'),
            '--link-mode', 'copy', '--keyring-provider', 'disabled', '--no-build',
            'pyarrow==21.0.0', 'tzdata==2026.4'])
    manifest_argv = [str(VENV / 'bin/python'), '-I', '-B', '-c', MANIFEST_CODE]
    before = json.loads(capture('04_manifest_before_check', manifest_argv))
    capture('05_pip_check', GLOBAL + ['pip', 'check', '--python', str(VENV / 'bin/python')])
    after = json.loads(capture('06_manifest_after_check', manifest_argv))
    stable = before == after
    after['before_after_pip_check_identical'] = stable
    after['manifest_scope'] = 'All regular public package and dist-info files owned by pyarrow/tzdata distributions; no symlink targets, pycache or other environment files hashed.'
    after['cache_origin_evidence'] = 'One successful uv offline install using explicit pre-existing local cache, copy links, keyring/config/build disabled; upstream source truth or independent custody not authenticated.'
    with (DOSSIER / 'environment_manifest.json').open('x') as stream:
        json.dump(after, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    setup['environment_manifest_sha256'] = digest(DOSSIER / 'environment_manifest.json')
    setup['python_version'] = after['python']['version']
    setup['distributions'] = after['distributions']
    setup['file_count'] = after['file_count']
    setup['regular_file_bytes'] = after['regular_file_bytes']
    setup['symlink_count'] = len(after['symlinks'])
    setup['before_after_pip_check_identical'] = stable
    if not stable:
        raise RuntimeError('distribution file manifests changed across uv pip check')
    setup['status'] = 'done'
except Exception as exc:
    setup['status'] = 'failed'
    setup['error'] = str(exc)
    setup['retryable'] = False
finally:
    setup['finished_at_utc'] = stamp()
    setup['retryable'] = False
    save()
print(json.dumps({key: setup.get(key) for key in ['status', 'error', 'python_version', 'file_count', 'regular_file_bytes', 'symlink_count', 'environment_manifest_sha256', 'before_after_pip_check_identical']}, sort_keys=True))
raise SystemExit(0 if setup['status'] == 'done' else 1)
