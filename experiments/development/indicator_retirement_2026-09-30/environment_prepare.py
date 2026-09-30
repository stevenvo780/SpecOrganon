"""Prepare D107 public dependencies once, offline, without installing specorganon.

The script records its exact executed source hash before invoking uv. It does not
claim that this source hash has been committed or has independent custody.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import time

DOSSIER = Path(__file__).resolve().parent
LOGS = DOSSIER / 'environment_setup'
SUMMARY = DOSSIER / 'environment_setup.json'
UV = Path('/home/dev/.local/bin/uv')
CACHE = '/home/dev/.cache/uv'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TZ': 'UTC',
       'PYTHONDONTWRITEBYTECODE': '1'}
GLOBAL = [str(UV), '--offline', '--no-config', '--no-python-downloads', '--cache-dir', CACHE]
BASES = {
    '311': Path('/tmp/specorganon-D102-install-cfoi0az2/venv-311/bin/python').resolve(strict=True),
    '312': Path('/tmp/specorganon-D102-install-cfoi0az2/venv-312/bin/python').resolve(strict=True),
}
EXPECTED_PYTHONS = {'311': '3.11.15', '312': '3.12.3'}
DEPENDENCIES = ['mcp==2.2.0', 'cryptography>=41,<51', 'pytest>=8,<10']

INVENTORY_CODE = r'''
from pathlib import Path
import base64,hashlib,importlib.metadata as md,json,os,stat,sys
venv=Path(sys.prefix).resolve()
expected_python=sys.argv[1]
version=sys.version.split()[0]
if version!=expected_python:raise RuntimeError('unexpected Python '+version)
distributions=sorted(md.distributions(),key=lambda d:d.metadata['Name'].lower())
versions={d.metadata['Name'].lower():d.version for d in distributions}
if 'specorganon' in versions:raise RuntimeError('specorganon must not be installed yet')
if versions.get('mcp')!='2.2.0':raise RuntimeError('mcp version differs')
if not 41<=int(versions['cryptography'].split('.')[0])<51:raise RuntimeError('cryptography outside declared range')
if not 8<=int(versions['pytest'].split('.')[0])<10:raise RuntimeError('pytest outside declared range')
out={'schema':1,'venv':str(venv),'python':{'version':version,'executable':sys.executable,'base_prefix':sys.base_prefix},'distributions':{},'files':{},'symlinks':[],'excluded_pycache':[],'record_validation':{'matched':0,'unhashed_entries':0,'mismatched':0},'specorganon_installed':False}
for d in distributions:
 name=d.metadata['Name'];filelist=d.files
 if filelist is None:raise RuntimeError('no RECORD file list for '+name)
 owned=[];nonregular=[]
 for rel in filelist:
  p=Path(os.path.abspath(d.locate_file(rel)))
  if not p.is_relative_to(venv):raise RuntimeError('distribution file outside venv '+str(p))
  key=str(p.relative_to(venv))
  if '__pycache__' in p.parts or p.suffix=='.pyc':
   if p.exists():out['excluded_pycache'].append({'path':key,'distribution':name})
   continue
  s=p.lstat()
  if stat.S_ISLNK(s.st_mode):
   out['symlinks'].append({'path':key,'distribution':name,'target':p.readlink().as_posix()});continue
  if not stat.S_ISREG(s.st_mode):nonregular.append(key);continue
  if not p.resolve().is_relative_to(venv):raise RuntimeError('resolved distribution path outside venv '+key)
  h=hashlib.sha256();size=0
  with p.open('rb') as f:
   for block in iter(lambda:f.read(1024*1024),b''):h.update(block);size+=len(block)
  result={'bytes':size,'sha256':h.hexdigest()}
  if key in out['files'] and out['files'][key]!=result:raise RuntimeError('conflicting file ownership '+key)
  out['files'][key]=result;owned.append(key)
  if rel.hash:
   encoded=base64.urlsafe_b64encode(h.digest()).decode().rstrip('=')
   if rel.hash.mode!='sha256' or rel.hash.value!=encoded or (rel.size is not None and rel.size!=size):
    out['record_validation']['mismatched']+=1;raise RuntimeError('installed RECORD mismatch '+key)
   out['record_validation']['matched']+=1
  else:out['record_validation']['unhashed_entries']+=1
 out['distributions'][name.lower()]={'version':d.version,'metadata_origin':str(d._path),'installer':(d.read_text('INSTALLER') or '').strip(),'regular_file_count':len(owned),'regular_file_bytes':sum(out['files'][x]['bytes'] for x in owned),'nonregular_entries':nonregular}
out['file_count']=len(out['files']);out['regular_file_bytes']=sum(x['bytes'] for x in out['files'].values());out['distribution_count']=len(out['distributions'])
out['inventory_scope']='Regular public files listed by installed distribution RECORDs, including their public dist-info and scripts; no interpreter symlinks, symlink targets, pycache, environment secrets or source repository imports.'
print(json.dumps(out,sort_keys=True,ensure_ascii=False,allow_nan=False))
'''


def now():
    return datetime.now(timezone.utc).isoformat()


def pin(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return {'bytes': Path(path).stat().st_size, 'sha256': h.hexdigest()}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               sort_keys=True, allow_nan=False) + '\n')


if SUMMARY.exists() or LOGS.exists():
    raise SystemExit('D107 setup outputs already exist; no overwrite or retry')
LOGS.mkdir()
runtime = Path(tempfile.mkdtemp(prefix='specorganon-D107-deps-', dir='/tmp'))
setup = {
    'schema': 1, 'study_id': 'D107', 'status': 'running', 'started_at_utc': now(),
    'runtime': str(runtime), 'dependencies_requested': DEPENDENCIES,
    'source_before_first_subprocess': {'path': str(Path(__file__).resolve()), **pin(__file__)},
    'prospective_plan': {'path': str(DOSSIER / 'plan.md'), 'registered_commit': '667a04b7e5a0d96e9df108757d068a26c5833b19', **pin(DOSSIER / 'plan.md')},
    'pyproject': {'path': '/workspace/SpecOrganon/pyproject.toml', **pin('/workspace/SpecOrganon/pyproject.toml')},
    'base_interpreters': {key: {'path': str(path), **pin(path)} for key, path in BASES.items()},
    'uv': {'path': str(UV), **pin(UV)}, 'cache': CACHE,
    'environment_allowlist': ENV, 'home_inherited_or_remapped': False,
    'offline': True, 'no_python_downloads': True, 'no_config': True,
    'no_build': True, 'keyring_provider': 'disabled', 'link_mode': 'copy',
    'attempts_per_environment': 1, 'retries': 0, 'auth_copied': False,
    'existing_environments_modified': False, 'specorganon_install_requested': False,
    'probe_executed': False, 'tests_executed': False, 'commands': [], 'environments': {},
    'source_git_freeze_claimed': False, 'independent_custody_authenticated': False,
}


def save():
    write_json(SUMMARY, setup)


def capture(name, argv):
    rec = {'name': name, 'argv': argv, 'cwd': str(runtime), 'environment': ENV,
           'started_at_utc': now()}
    started = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=runtime, env=ENV, capture_output=True,
                                timeout=60, check=False)
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code = exc.stdout or b'', exc.stderr or b'', None
        rec['error'] = '60 second timeout; no retry'
    except OSError as exc:
        stdout, stderr, code = b'', b'', None
        rec['error'] = str(exc)
    rec.update({'finished_at_utc': now(), 'wall_seconds_local': time.monotonic() - started,
                'exit_code': code})
    for label, data in [('stdout', stdout), ('stderr', stderr)]:
        path = LOGS / (name + '.' + label)
        with path.open('xb') as stream:
            stream.write(data)
        rec[label] = {'path': str(path), 'bytes': len(data),
                      'sha256': hashlib.sha256(data).hexdigest()}
    write_json(LOGS / (name + '.command.json'), rec)
    setup['commands'].append(rec)
    save()
    if code != 0:
        raise RuntimeError(name + ' failed, exit=' + str(code))
    return stdout


try:
    save()
    capture('00_uv_version', [str(UV), '--version'])
    for label, base in BASES.items():
        expected = EXPECTED_PYTHONS[label]
        version = capture(label + '_01_base_version', [str(base), '-I', '-B', '-c',
                          'import sys; print(sys.version.split()[0])']).decode().strip()
        if version != expected:
            raise RuntimeError('base interpreter version differs: ' + label + ' ' + version)
        venv = runtime / ('venv-' + label)
        capture(label + '_02_venv', GLOBAL + ['venv', '--python', str(base), str(venv)])
        capture(label + '_03_install', GLOBAL + ['pip', 'install', '--python', str(venv / 'bin/python'),
                '--link-mode', 'copy', '--keyring-provider', 'disabled', '--no-build', *DEPENDENCIES])
        inventory_argv = [str(venv / 'bin/python'), '-I', '-B', '-c', INVENTORY_CODE, expected]
        before = json.loads(capture(label + '_04_inventory_before_check', inventory_argv))
        capture(label + '_05_pip_check', GLOBAL + ['pip', 'check', '--python', str(venv / 'bin/python')])
        after = json.loads(capture(label + '_06_inventory_after_check', inventory_argv))
        if before != after:
            raise RuntimeError('inventory differs across pip check: ' + label)
        inventory_path = LOGS / (label + '.inventory.json')
        after['before_after_pip_check_identical'] = True
        write_json(inventory_path, after)
        setup['environments'][label] = {
            'venv': str(venv), 'python': str(venv / 'bin/python'), 'python_version': version,
            'inventory': {'path': str(inventory_path), **pin(inventory_path)},
            'distribution_count': after['distribution_count'], 'file_count': after['file_count'],
            'regular_file_bytes': after['regular_file_bytes'],
            'distributions': after['distributions'], 'symlinks': after['symlinks'],
            'excluded_pycache_count': len(after['excluded_pycache']),
            'record_validation': after['record_validation'],
            'before_after_pip_check_identical': True, 'specorganon_installed': False,
        }
        save()
    setup['source_after_setup'] = {'path': str(Path(__file__).resolve()), **pin(__file__)}
    setup['executed_source_unchanged'] = setup['source_before_first_subprocess'] == setup['source_after_setup']
    if not setup['executed_source_unchanged']:
        raise RuntimeError('environment preparer source changed during setup')
    setup['status'] = 'done'
except Exception as exc:
    setup['status'] = 'failed'
    setup['error'] = str(exc)
finally:
    setup['finished_at_utc'] = now()
    setup['retryable'] = False
    save()
print(json.dumps({'status': setup['status'], 'error': setup.get('error'), 'runtime': str(runtime),
                  'source_sha256': setup['source_before_first_subprocess']['sha256'],
                  'environments': {k: {x: v[x] for x in ['python', 'python_version', 'inventory', 'distribution_count', 'file_count', 'regular_file_bytes']} for k,v in setup['environments'].items()}}, sort_keys=True))
raise SystemExit(0 if setup['status'] == 'done' else 1)
