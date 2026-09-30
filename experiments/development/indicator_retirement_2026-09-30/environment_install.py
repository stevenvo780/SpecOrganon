"""One-attempt offline build/install of D107, retaining exact public evidence.

No toolkit tests, probes, source-row analysis, source edits or old-env installs.
"""
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path
import configparser
import hashlib
import io
import json
import os
import stat
import subprocess
import time
import tomllib
import zipfile

REPO = Path('/workspace/SpecOrganon')
DOSSIER = Path(__file__).resolve().parent
LOGS = DOSSIER / 'environment_install_repaired'
SUMMARY = DOSSIER / 'environment_install_repaired.json'
OUTPUT = DOSSIER / 'installed_repaired'
WHEEL = OUTPUT / 'specorganon-0.1.0-py3-none-any.whl'
UV = '/home/dev/.local/bin/uv'
CACHE = '/home/dev/.cache/uv'
ENGINE_SHA = '679e3885d7e72bec8af8a032c5b3264acfd514c0962e13ea17b3bbbc8bd2c6cf'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TZ': 'UTC',
       'PYTHONDONTWRITEBYTECODE': '1'}
GLOBAL = [UV, '--offline', '--no-config', '--no-python-downloads', '--cache-dir', CACHE]

INVENTORY_CODE = r'''
from pathlib import Path
import base64,hashlib,importlib.metadata as md,json,os,stat,sys
venv=Path(sys.prefix).resolve()
if sys.version.split()[0]!=sys.argv[1]:raise RuntimeError('Python version differs')
distributions=sorted(md.distributions(),key=lambda d:d.metadata['Name'].lower())
versions={d.metadata['Name'].lower():d.version for d in distributions}
if versions.get('specorganon')!='0.1.0':raise RuntimeError('new specorganon missing or wrong version')
out={'schema':1,'venv':str(venv),'python':{'version':sys.version.split()[0],'executable':sys.executable,'base_prefix':sys.base_prefix},'versions':versions,'distributions':{},'files':{},'symlinks':[],'excluded_pycache':[],'record_validation':{'matched':0,'unhashed_entries':0,'mismatched':0}}
for d in distributions:
 name=d.metadata['Name'].lower();filelist=d.files
 if filelist is None:raise RuntimeError('missing RECORD list '+name)
 owned=[];listed=set()
 for rel in filelist:
  p=Path(os.path.abspath(d.locate_file(rel)))
  if not p.is_relative_to(venv):raise RuntimeError('package file outside venv '+str(p))
  key=str(p.relative_to(venv));listed.add(key)
  if '__pycache__' in p.parts or p.suffix=='.pyc':
   if p.exists():out['excluded_pycache'].append({'path':key,'distribution':name})
   continue
  s=p.lstat()
  if stat.S_ISLNK(s.st_mode):
   out['symlinks'].append({'path':key,'distribution':name,'target':p.readlink().as_posix()});continue
  if not stat.S_ISREG(s.st_mode):raise RuntimeError('nonregular distribution file '+key)
  if not p.resolve().is_relative_to(venv):raise RuntimeError('resolved package file outside venv '+key)
  h=hashlib.sha256();n=0
  with p.open('rb') as f:
   for block in iter(lambda:f.read(1024*1024),b''):h.update(block);n+=len(block)
  value={'bytes':n,'sha256':h.hexdigest()}
  if key in out['files'] and out['files'][key]!=value:raise RuntimeError('conflicting package file '+key)
  out['files'][key]=value;owned.append(key)
  if rel.hash:
   encoded=base64.urlsafe_b64encode(h.digest()).decode().rstrip('=')
   if rel.hash.mode!='sha256' or rel.hash.value!=encoded or (rel.size is not None and rel.size!=n):
    out['record_validation']['mismatched']+=1;raise RuntimeError('installed RECORD mismatch '+key)
   out['record_validation']['matched']+=1
  else:out['record_validation']['unhashed_entries']+=1
 out['distributions'][name]={'version':d.version,'metadata_origin':str(d._path),'installer':(d.read_text('INSTALLER') or '').strip(),'regular_file_count':len(owned),'regular_file_bytes':sum(out['files'][x]['bytes'] for x in owned)}
 if name=='specorganon':
  out['specorganon']={'metadata_origin':str(d._path),'entrypoints':{e.name:e.value for e in d.entry_points if e.group=='console_scripts'},'direct_url':json.loads(d.read_text('direct_url.json'))}
  roots=[Path(d.locate_file('specorganon')),Path(d._path)]
  for root in roots:
   for p in root.rglob('*'):
    if '__pycache__' in p.parts or p.suffix=='.pyc':continue
    if p.is_symlink():raise RuntimeError('unexpected specorganon symlink '+str(p))
    if p.is_file() and str(p.relative_to(venv)) not in listed:raise RuntimeError('unlisted installed specorganon file '+str(p))
out['distribution_count']=len(out['distributions']);out['file_count']=len(out['files']);out['regular_file_bytes']=sum(x['bytes'] for x in out['files'].values())
out['inventory_scope']='All regular public distribution RECORD files including normalized venv/bin scripts and dist-info; no pycache, symlink targets, interpreter environment contents or repository imports.'
print(json.dumps(out,sort_keys=True,ensure_ascii=False,allow_nan=False))
'''


def now():
    return datetime.now(timezone.utc).isoformat()


def pin_bytes(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def regular(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('not a regular public file: ' + str(path))
    return path.read_bytes()


def pin(path):
    return pin_bytes(regular(Path(path)))


def expected(row):
    return {key: row[key] for key in ('bytes', 'sha256')}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n')


def source_pins():
    files = sorted((REPO / 'src/specorganon').rglob('*.py'))
    require(len(files) == 24, 'expected exactly 24 production source modules')
    result = {}
    for path in files:
        require(path.resolve(strict=True).is_relative_to(REPO / 'src/specorganon'), 'production source outside package')
        result[str(path.relative_to(REPO))] = pin(path)
    require(result['src/specorganon/engine.py']['sha256'] == ENGINE_SHA, 'final core engine pin differs')
    result['README.md'] = pin(REPO / 'README.md')
    result['pyproject.toml'] = pin(REPO / 'pyproject.toml')
    return result


def verify_dependencies(inventory):
    venv = Path(inventory['venv']).resolve(strict=True)
    for name, row in inventory['files'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'noncanonical original package path')
        path = venv / name
        require(path.resolve(strict=True).is_relative_to(venv), 'original dependency outside venv')
        require(pin(path) == expected(row), 'original dependency bytes changed: ' + name)
    return len(inventory['files'])


def verify_wheel(raw, before):
    result = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'duplicate wheel member name')
        modules = {name for name in names if name.startswith('specorganon/') and name.endswith('.py')}
        expected_modules = {name.removeprefix('src/') for name in before if name.startswith('src/specorganon/')}
        require(len(modules) == 24 and modules == expected_modules, 'wheel/source module inventory differs')
        for name in sorted(modules):
            module_raw = archive.read(name)
            require(pin_bytes(module_raw) == before['src/' + name] and module_raw == regular(REPO / 'src' / name),
                    'wheel module differs from current verified source: ' + name)
            result[name] = pin_bytes(module_raw)
        info = 'specorganon-0.1.0.dist-info/'
        metadata = BytesParser().parsebytes(archive.read(info + 'METADATA'))
        require(metadata['Name'] == 'specorganon' and metadata['Version'] == '0.1.0', 'wheel metadata name/version differs')
        dependencies = metadata.get_all('Requires-Dist') or []
        require('mcp==2.2.0' in dependencies and 'cryptography<51,>=41' in dependencies,
                'wheel dependencies differ from pyproject ranges')
        require(not any(not ('extra ==' in row or row in {'mcp==2.2.0', 'cryptography<51,>=41'}) for row in dependencies),
                'wheel added undeclared core dependency')
        entrypoints = configparser.ConfigParser()
        entrypoints.read_string(archive.read(info + 'entry_points.txt').decode())
        scripts = dict(entrypoints['console_scripts'])
        require(scripts == {'organon': 'specorganon.cli:main', 'organon-mcp': 'specorganon.server:main'},
                'wheel console entrypoints differ')
        require(metadata['Requires-Python'] == '>=3.11', 'wheel Python requirement differs')
        return {'modules': result, 'module_count': len(result), 'metadata': {'name': metadata['Name'],
                'version': metadata['Version'], 'requires_python': metadata['Requires-Python'],
                'requires_dist': dependencies, 'console_scripts': scripts}, 'all_source_modules_match': True}


if SUMMARY.exists() or LOGS.exists() or OUTPUT.exists():
    raise SystemExit('D107 install/build output exists; no overwrite or automatic retry')
prepared = json.loads(regular(DOSSIER / 'environment_setup.json'))
require(prepared['status'] == 'done', 'dependency environment preparation did not succeed')
recipe = tomllib.loads(regular(REPO / 'pyproject.toml').decode())
require(recipe['project']['dependencies'] == ['cryptography>=41,<51', 'mcp==2.2.0'], 'declared dependencies differ')
uv_resolved = Path(UV).resolve(strict=True)
uv_pin = pin(uv_resolved)
LOGS.mkdir()
OUTPUT.mkdir()
setup = {'schema': 1, 'study_id': 'D107', 'status': 'running', 'started_at_utc': now(),
         'runtime': prepared['runtime'], 'source_before_first_subprocess': {'path': str(Path(__file__).resolve()), **pin(__file__)},
         'production_and_recipe_before': source_pins(), 'environment_setup_pin': pin(DOSSIER / 'environment_setup.json'),
         'plan_pin': pin(DOSSIER / 'plan.md'), 'environment_allowlist': ENV,
         'repair_plan': {'path': str(DOSSIER / 'build_repair_plan.md'), 'commit': 'a26b15b', **pin(DOSSIER / 'build_repair_plan.md')},
         'preserved_initial_failure': {'path': str(DOSSIER / 'environment_install.json'), **pin(DOSSIER / 'environment_install.json')},
         'original_failed_directories_kept': [str(DOSSIER / 'environment_install'), str(DOSSIER / 'installed')],
         'home_inherited_or_remapped': False, 'auth_copied': False, 'offline': True,
         'no_config': True, 'no_python_downloads': True, 'install_no_deps': True,
         'install_no_build': True, 'install_keyring_provider': 'disabled', 'link_mode': 'copy',
         'compile_bytecode_requested': False, 'attempts_build': 1, 'attempts_install_each': 1,
         'automatic_retry': False, 'old_D102_environments_modified': False,
         'tests_executed': False, 'probes_executed': False, 'raw_row_analysis_executed': False,
         'commands': [], 'environments': {}, 'original_dependency_checks_before': {},
         'uv': {'invoked_path': UV, 'resolved_path': str(uv_resolved), **uv_pin}, 'cache': CACHE}
originals = {}


def save():
    write_json(SUMMARY, setup)


def capture(name, argv, cwd):
    rec = {'name': name, 'argv': argv, 'cwd': str(cwd), 'environment': ENV, 'started_at_utc': now()}
    began = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=cwd, env=ENV, capture_output=True, timeout=120, check=False)
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code = exc.stdout or b'', exc.stderr or b'', None
        rec['error'] = '120 second terminal timeout; no retry'
    except OSError as exc:
        stdout, stderr, code = b'', b'', None
        rec['error'] = str(exc)
    rec.update(finished_at_utc=now(), wall_seconds_local=time.monotonic() - began, exit_code=code)
    for label, raw in [('stdout', stdout), ('stderr', stderr)]:
        path = LOGS / (name + '.' + label)
        with path.open('xb') as stream:
            stream.write(raw)
        rec[label] = {'path': str(path), **pin_bytes(raw)}
    write_json(LOGS / (name + '.command.json'), rec)
    setup['commands'].append(rec)
    save()
    require(code == 0, 'terminal command failure: ' + name + ', exit=' + str(code))
    return stdout


try:
    save()
    for label, environment in prepared['environments'].items():
        row = environment['inventory']
        raw = regular(Path(row['path']))
        require(pin_bytes(raw) == expected(row), 'original dependency inventory pin differs')
        original = json.loads(raw)
        require(len(original['distributions']) == 33 and 'specorganon' not in original['distributions'],
                'prepared environment inventory already includes toolkit or wrong dependency count')
        originals[label] = original
        setup['original_dependency_checks_before'][label] = {'inventory_pin': expected(row),
                    'verified_file_count': verify_dependencies(original)}
    save()
    build_python = prepared['base_interpreters']['311']['path']
    capture('01_build', GLOBAL + ['build', '--wheel', '--no-sources', '--python', build_python,
                                 '--out-dir', str(OUTPUT)], REPO)
    require(sorted(p.name for p in OUTPUT.glob('*.whl')) == [WHEEL.name], 'build produced unexpected wheel outputs')
    setup['build_output_files'] = {str(path.relative_to(OUTPUT)): pin(path)
                                   for path in sorted(OUTPUT.rglob('*')) if path.is_file()}
    wheel_raw = regular(WHEEL)
    setup['wheel'] = {'path': str(WHEEL.relative_to(REPO)), **pin_bytes(wheel_raw)}
    setup['wheel_verification'] = verify_wheel(wheel_raw, setup['production_and_recipe_before'])
    save()
    for label, environment in prepared['environments'].items():
        python = environment['python']
        venv = Path(python).absolute().parent.parent
        require(pin(WHEEL) == expected(setup['wheel']), 'actual wheel changed before install')
        capture(label + '_02_install', GLOBAL + ['pip', 'install', '--python', python, '--no-deps',
                 '--link-mode', 'copy', '--keyring-provider', 'disabled', '--no-build', str(WHEEL)], Path(prepared['runtime']))
        capture(label + '_03_pip_check', GLOBAL + ['pip', 'check', '--python', python], Path(prepared['runtime']))
        inventory_raw = capture(label + '_04_inventory', [python, '-I', '-B', '-c', INVENTORY_CODE,
                                                        environment['python_version']], Path(prepared['runtime']))
        installed = json.loads(inventory_raw)
        require(installed['distribution_count'] == 34 and not installed['symlinks'] and not installed['excluded_pycache'],
                'installed distribution count, symlinks or pycache differs')
        previous = originals[label]
        require({name: row['version'] for name, row in previous['distributions'].items()} ==
                {name: version for name, version in installed['versions'].items() if name != 'specorganon'},
                'original dependency versions changed')
        require(all(installed['files'].get(name) == row for name, row in previous['files'].items()),
                'original dependency file pins changed in full inventory')
        verify_dependencies(previous)
        require(installed['specorganon']['entrypoints'] == setup['wheel_verification']['metadata']['console_scripts'],
                'installed entrypoint metadata differs from verified wheel')
        from urllib.parse import unquote, urlparse
        direct = installed['specorganon']['direct_url']
        url = urlparse(direct['url'])
        require(url.scheme == 'file' and Path(unquote(url.path)).resolve(strict=True) == WHEEL.resolve(strict=True),
                'installed package did not originate in the actual new local wheel')
        archive_hash = direct.get('archive_info', {}).get('hashes', {}).get('sha256')
        if archive_hash is not None:
            require(archive_hash == setup['wheel']['sha256'], 'installed wheel provenance hash differs')
        purelib = Path(installed['specorganon']['metadata_origin']).parent
        actual_modules = {str(p.relative_to(purelib)): pin(p) for p in (purelib / 'specorganon').rglob('*.py')}
        require(actual_modules == setup['wheel_verification']['modules'], 'installed 24-module inventory differs from new wheel')
        entrypoints = {}
        for name in ('organon', 'organon-mcp'):
            path = venv / 'bin' / name
            require(path.resolve(strict=True).is_relative_to(venv) and os.access(path, os.X_OK), 'installed entrypoint outside venv or not executable')
            entrypoints[name] = {'path': str(path), **pin(path)}
        installed['original_33_dependency_files_unchanged'] = True
        installed['verified_original_dependency_file_count'] = len(previous['files'])
        installed['wheel_pin'] = expected(setup['wheel'])
        inventory_path = LOGS / (label + '.installed_inventory.json')
        write_json(inventory_path, installed)
        setup['environments'][label] = {'python': python, 'cli': str(venv / 'bin/organon'), 'mcp': str(venv / 'bin/organon-mcp'),
            'entrypoints': entrypoints, 'inventory': environment['inventory'],
            'installed_inventory': {'path': str(inventory_path), **pin(inventory_path)},
            'distribution_count': installed['distribution_count'], 'file_count': installed['file_count'],
            'regular_file_bytes': installed['regular_file_bytes'], 'versions': installed['versions'],
            'installed_modules': actual_modules, 'direct_url': direct,
            'original_33_dependency_files_unchanged': True}
        save()
    require(pin(WHEEL) == expected(setup['wheel']), 'new wheel changed across installation')
    setup['status'] = 'done'
except Exception as exc:
    setup['status'] = 'failed'
    setup['error'] = f'{type(exc).__name__}: {exc}'
finally:
    try:
        setup['production_and_recipe_after'] = source_pins()
        setup['production_and_recipe_unchanged'] = setup['production_and_recipe_before'] == setup['production_and_recipe_after']
        require(setup['production_and_recipe_unchanged'], 'production/README/pyproject changed during build/install')
        setup['executed_source_after'] = {'path': str(Path(__file__).resolve()), **pin(__file__)}
        setup['executed_source_unchanged'] = setup['source_before_first_subprocess'] == setup['executed_source_after']
        require(setup['executed_source_unchanged'], 'build/install runner source changed')
        setup['uv_after'] = {'resolved_path': str(Path(UV).resolve(strict=True)), **pin(Path(UV).resolve(strict=True))}
        require(setup['uv_after']['resolved_path'] == str(uv_resolved) and expected(setup['uv_after']) == uv_pin,
                'public uv executable changed during corrected build/install')
        setup['original_dependency_checks_after'] = {label: {'verified_file_count': verify_dependencies(original)}
                                                    for label, original in originals.items()}
    except Exception as exc:
        setup['status'] = 'failed'
        setup['preservation_error'] = f'{type(exc).__name__}: {exc}'
    setup['finished_at_utc'] = now()
    setup['retryable'] = False
    save()
print(json.dumps({'status': setup['status'], 'error': setup.get('error'), 'preservation_error': setup.get('preservation_error'),
                  'wheel': setup.get('wheel'), 'runtime': setup['runtime'],
                  'environments': {label: {key: env[key] for key in ('python', 'distribution_count', 'file_count', 'regular_file_bytes', 'installed_inventory')}
                                   for label, env in setup['environments'].items()}}, sort_keys=True))
raise SystemExit(0 if setup['status'] == 'done' else 1)
