"""Synthetic wheel/bootstrap controls only; no native qualification evidence."""
import base64
import csv
import io
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
from types import ModuleType

import pytest

from specorganon import t_native_entry as entry


VERSION = '0.2.0rc3.dev12'
ENTRY = Path(entry.__file__)


def write_record(site_root, metadata):
    rows = []
    for path in sorted(site_root.rglob('*')):
        if path.is_file() and path.suffix != '.pyc' and path.name != 'RECORD':
            raw = path.read_bytes()
            pin = base64.urlsafe_b64encode(bytes.fromhex(entry.sha(raw))).rstrip(b'=').decode()
            rows.append((path.relative_to(site_root).as_posix(), 'sha256=' + pin, len(raw)))
    rows.append((metadata.relative_to(site_root).as_posix() + '/RECORD', '', ''))
    stream = io.StringIO()
    csv.writer(stream).writerows(rows)
    (metadata / 'RECORD').write_text(stream.getvalue())


@pytest.fixture
def synthetic_wheel(tmp_path):
    """Explicit artificial site/metadata/pilot, never a native run or real install."""
    site_root = tmp_path / 'environment/lib/site-packages'
    package = site_root / 'specorganon'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('__version__ = ' + repr(VERSION) + '\n')
    (package / 't_native_entry.py').write_bytes(ENTRY.read_bytes())
    (package / 'payload.py').write_text('VALUE = "fresh"\n')
    (package / 't_native_pilot.py').write_text(
        'from .payload import VALUE\n'
        'def execute(plan, expected, operation, *, installed_root):\n'
        '    return {"status": "incomplete", "goal_achieved": False,\n'
        '            "synthetic": True, "value": VALUE, "operation": operation,\n'
        '            "installed_root": str(installed_root)}\n')
    metadata = site_root / ('specorganon-' + VERSION + '.dist-info')
    metadata.mkdir()
    (metadata / 'WHEEL').write_text('Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
    (metadata / 'METADATA').write_text('Metadata-Version: 2.1\nName: specorganon\nVersion: ' + VERSION + '\n')
    write_record(site_root, metadata)
    source = tmp_path / 'source'
    source_package = source / 'src/specorganon'
    source_package.mkdir(parents=True)
    for path in package.glob('*.py'):
        (source_package / path.name).write_bytes(path.read_bytes())
    plan = {
        'schema': 1, 'protocol': 'T-native-development-v1',
        'classification': 'prospective public T native development',
        'candidate_version': VERSION, 'source_root': str(source),
        'source_sha256': {'src/specorganon/' + p.name: entry.sha(p.read_bytes())
                          for p in source_package.glob('*.py')},
    }
    return site_root, package, metadata, source, plan


def fresh(fixture, tmp_path, *, before='', expected=None, isolated=True, fake_distribution=''):
    site_root, package, metadata, source, plan = fixture
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(plan))
    pin = entry.sha(path.read_bytes()) if expected is None else expected
    # PathDistribution reads actual synthetic WHEEL/METADATA/RECORD files. The
    # site discovery override is explicit: this fixture is not wheel acceptance.
    script = (
        'import sys, importlib.metadata, sysconfig\nfrom pathlib import Path\n'
        f'sys.path.insert(0, {str(site_root)!r})\n'
        f'dist = importlib.metadata.Distribution.at({str(metadata)!r})\n'
        'importlib.metadata.distribution = lambda name: dist\n'
        'original_get_path = sysconfig.get_path\n'
        f'sysconfig.get_path = lambda name: {str(site_root)!r} if name in ("purelib", "platlib") else original_get_path(name)\n'
        + fake_distribution + '\n' + before + '\n'
        'from specorganon.t_native_entry import main\n'
        f'sys.argv = ["organon-t-native", "report", {str(path)!r}, "--plan-sha256", {pin!r}]\n'
        'sys.exit(main())\n')
    command = [sys.executable, *(['-I', '-B'] if isolated else []), '-c', script]
    return subprocess.run(command, capture_output=True, text=True, timeout=15)


def rejected(result, message=None):
    assert result.returncode == 2, (result.stdout, result.stderr)
    value = json.loads(result.stderr)
    assert value['status'] == 'rejected' and value['goal_achieved'] is False
    if message:
        assert message in value['reason']
    assert not result.stdout
    return value


@pytest.mark.parametrize('isolated', [True, False])
def test_synthetic_installed_report_and_normal_console_flags(synthetic_wheel, tmp_path, isolated):
    result = fresh(synthetic_wheel, tmp_path, isolated=isolated)
    assert result.returncode == 2 and not result.stderr, result.stderr
    report = json.loads(result.stdout)
    assert report['synthetic'] is True and report['status'] == 'incomplete'
    assert report['goal_achieved'] is False and report['value'] == 'fresh'
    assert report['installed_root'] == str(synthetic_wheel[1])


def test_synthetic_launch_ignores_same_size_same_mtime_stale_pyc(synthetic_wheel, tmp_path):
    path = synthetic_wheel[1] / 'payload.py'
    original = path.read_bytes()
    mtime = path.stat().st_mtime_ns
    path.write_bytes(original.replace(b'fresh', b'stale'))
    os.utime(path, ns=(mtime, mtime))
    py_compile.compile(str(path), doraise=True)
    path.write_bytes(original)
    os.utime(path, ns=(mtime, mtime))
    result = fresh(synthetic_wheel, tmp_path)
    assert result.returncode == 2 and not result.stderr, result.stderr
    assert json.loads(result.stdout)['value'] == 'fresh'


def loader_fixture(tmp_path):
    package = tmp_path / 'installed/specorganon'
    source = tmp_path / 'source'
    source_package = source / 'src/specorganon'
    package.mkdir(parents=True)
    source_package.mkdir(parents=True)
    for root in (package, source_package):
        (root / '__init__.py').write_text('')
        (root / 'payload.py').write_text('VALUE = "first"\n')
    bindings = {'src/specorganon/' + p.name: entry.sha(p.read_bytes()) for p in package.glob('*.py')}
    return package, source, bindings


def test_snapshot_compiles_pinned_bytes_despite_stale_pyc_and_later_changes(tmp_path):
    package, source, bindings = loader_fixture(tmp_path)
    path = package / 'payload.py'
    mtime = path.stat().st_mtime_ns
    py_compile.compile(str(path), doraise=True)
    path.write_text('VALUE = "other"\n')
    os.utime(path, ns=(mtime, mtime))
    assert path.stat().st_size == len('VALUE = "first"\n')
    (source / 'src/specorganon/payload.py').write_bytes(path.read_bytes())
    bindings['src/specorganon/payload.py'] = entry.sha(path.read_bytes())
    loader = entry.InstalledSources(package, source, bindings)
    path.write_text('raise RuntimeError("must never execute")\n')
    (source / 'src/specorganon/payload.py').write_text('raise RuntimeError("source also changed")\n')
    module = ModuleType('specorganon.payload')
    loader.exec_module(module)
    assert module.VALUE == 'other'
    assert module.__registered_source_sha256__ == bindings['src/specorganon/payload.py']


@pytest.mark.parametrize('fault', ['installed_extra', 'source_extra', 'missing_pin', 'byte_drift', 'missing_init'])
def test_loader_rejects_inventory_or_bytes_before_execution(tmp_path, fault):
    package, source, bindings = loader_fixture(tmp_path)
    if fault == 'installed_extra':
        (package / 'unregistered.py').write_text('raise RuntimeError("never")')
    elif fault == 'source_extra':
        (source / 'src/specorganon/unregistered.py').write_text('raise RuntimeError("never")')
    elif fault == 'missing_pin':
        bindings.pop('src/specorganon/payload.py')
    elif fault == 'missing_init':
        bindings.pop('src/specorganon/__init__.py')
    else:
        (package / 'payload.py').write_text('raise RuntimeError("never")')
    with pytest.raises(ValueError, match='inventories differ|differs from pinned'):
        entry.InstalledSources(package, source, bindings)


def test_snapshot_finder_blocks_filesystem_fallback_and_detects_added_inventory(tmp_path):
    package, source, bindings = loader_fixture(tmp_path)
    loader = entry.InstalledSources(package, source, bindings)
    (package / 'unregistered.py').write_text('raise RuntimeError("never")')
    with pytest.raises(ImportError, match='no filesystem fallback'):
        loader.find_spec('specorganon.unregistered')
    with pytest.raises(ValueError, match='inventory changed'):
        loader.check_inventory()
    assert loader.find_spec('unrelated') is None


@pytest.mark.parametrize('fault', ['editable', 'ambiguous_editable', 'wheel_missing', 'version',
                                 'record_missing_module', 'record_hash', 'record_location',
                                 'record_missing_file', 'record_symlink', 'metadata_identity',
                                 'checkout_equal_bytes', 'outside_site', 'preimport', 'source_drift',
                                 'installed_drift', 'inventory_drift', 'missing_execute'])
def test_synthetic_admission_rejections(synthetic_wheel, tmp_path, fault):
    site_root, package, metadata, source, plan = synthetic_wheel
    before = fake = ''
    if fault in ('editable', 'ambiguous_editable'):
        info = {'editable': True} if fault == 'editable' else {}
        (metadata / 'direct_url.json').write_text(json.dumps({'url': source.as_uri(), 'dir_info': info}))
        write_record(site_root, metadata)
    elif fault == 'wheel_missing':
        (metadata / 'WHEEL').unlink()
        write_record(site_root, metadata)
    elif fault == 'version':
        plan['candidate_version'] = '0.2.0rc3.dev11'
    elif fault == 'record_missing_module':
        record = metadata / 'RECORD'
        record.write_text(''.join(line for line in record.read_text().splitlines(True)
                                 if not line.startswith('specorganon/payload.py,')))
    elif fault == 'record_hash':
        record = metadata / 'RECORD'
        rows = list(csv.reader(io.StringIO(record.read_text())))
        for row in rows:
            if row[0] == 'specorganon/payload.py':
                row[1] = 'sha256=' + 'a' * 43
        stream = io.StringIO(); csv.writer(stream).writerows(rows); record.write_text(stream.getvalue())
    elif fault == 'record_missing_file':
        with (metadata / 'RECORD').open('a') as stream:
            stream.write('specorganon/nonexistent.py,sha256=' + 'a' * 43 + ',42\n')
    elif fault == 'record_symlink':
        record = metadata / 'RECORD'
        target = tmp_path / 'foreign-record'; record.rename(target); record.symlink_to(target)
    elif fault == 'metadata_identity':
        (metadata / 'METADATA').write_text('Name: other-project\nVersion: ' + VERSION + '\n')
    elif fault == 'record_location':
        fake = ('original_locate = dist.locate_file\n'
                f'dist.locate_file = lambda item: Path({str(source / "src/specorganon/payload.py")!r}) if str(item) == "specorganon/payload.py" else original_locate(item)\n')
    elif fault == 'checkout_equal_bytes':
        before = f'sys.path.insert(0, {str(source / "src")!r})\n'
    elif fault == 'outside_site':
        fake = 'sysconfig.get_path = lambda name: "/unrelated/site-packages"\n'
    elif fault == 'preimport':
        before = 'import specorganon.payload\n'
    elif fault == 'source_drift':
        (source / 'src/specorganon/payload.py').write_text('raise RuntimeError("never")')
    elif fault == 'installed_drift':
        (package / 'payload.py').write_text('raise RuntimeError("never")')
    elif fault == 'inventory_drift':
        (package / 'extra.py').write_text('raise RuntimeError("never")')
    else:
        for root in (package, source / 'src/specorganon'):
            (root / 't_native_pilot.py').write_text('# Synthetic not-yet-implemented pilot\n')
        plan['source_sha256']['src/specorganon/t_native_pilot.py'] = entry.sha((package / 't_native_pilot.py').read_bytes())
        write_record(site_root, metadata)
    rejection = rejected(fresh(synthetic_wheel, tmp_path, before=before, fake_distribution=fake))
    assert 'RuntimeError' not in rejection['reason']


def test_explicit_noneditable_directory_metadata(synthetic_wheel, tmp_path):
    site_root, package, metadata, source, plan = synthetic_wheel
    (metadata / 'direct_url.json').write_text(json.dumps({'url': source.as_uri(), 'dir_info': {'editable': False}}))
    write_record(site_root, metadata)
    result = fresh(synthetic_wheel, tmp_path)
    assert result.returncode == 2 and not result.stderr
    assert json.loads(result.stdout)['synthetic'] is True


@pytest.mark.parametrize(('field', 'value'), [
    ('schema', True), ('schema', 1.0), ('schema', '1'), ('protocol', 1),
    ('protocol', 'other'), ('classification', 'other'), ('candidate_version', 12),
    ('source_root', []), ('source_root', 'relative'), ('source_sha256', []),
    ('source_sha256', {}), ('source_sha256', {'../escape': 'a' * 64}),
    ('source_sha256', {'src/specorganon/payload.py': True}),
])
def test_exact_plan_types_and_paths(synthetic_wheel, tmp_path, field, value):
    synthetic_wheel[4][field] = value
    rejected(fresh(synthetic_wheel, tmp_path))


@pytest.mark.parametrize('pin', ['a' * 63, 'a' * 65, 'A' * 64, 'g' * 64, 'a' * 64 + '\n', 'sha256:' + 'a' * 64])
def test_external_digest_is_strict_before_imports(synthetic_wheel, tmp_path, pin):
    rejected(fresh(synthetic_wheel, tmp_path, expected=pin), 'exact lowercase SHA256')


def test_wrong_external_digest(synthetic_wheel, tmp_path):
    rejected(fresh(synthetic_wheel, tmp_path, expected='0' * 64), 'digest differs before imports')


@pytest.mark.parametrize('raw', [b'{"schema":1,"schema":1}', b'{"nested":{"x":1,"x":2}}',
                               b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e999}'])
def test_json_duplicates_and_nonfinite_rejected(raw):
    with pytest.raises(ValueError):
        entry.exact_json(raw)


@pytest.mark.parametrize('fault', ['file_symlink', 'directory_symlink', 'hardlink', 'oversize', 'fifo', 'parent'])
def test_read_regular_rejects_unsafe_paths_and_types(tmp_path, fault):
    parent = tmp_path / 'directory'; parent.mkdir()
    path = parent / 'file'; path.write_bytes(b'bytes')
    if fault == 'file_symlink':
        target = tmp_path / 'target'; target.write_bytes(b'bytes'); path.unlink(); path.symlink_to(target)
    elif fault == 'directory_symlink':
        target = tmp_path / 'target'; parent.rename(target); parent.symlink_to(target, target_is_directory=True)
    elif fault == 'hardlink':
        (tmp_path / 'alias').hardlink_to(path)
    elif fault == 'fifo':
        path.unlink(); os.mkfifo(path)
    elif fault == 'parent':
        path = parent / '..' / 'directory/file'
    with pytest.raises((ValueError, OSError)):
        entry.read_regular(path, limit=4 if fault == 'oversize' else 100)


@pytest.mark.parametrize('change', ['same_length_bytes', 'file_replacement', 'parent_replacement', 'hardlink_added'])
def test_read_regular_detects_changes_while_descriptor_is_held(tmp_path, monkeypatch, change):
    parent = tmp_path / 'directory'; parent.mkdir()
    path = parent / 'file'; path.write_bytes(b'first')
    original_read = os.read
    done = False

    def racing_read(fd, size):
        nonlocal done
        raw = original_read(fd, size)
        if not done:
            done = True
            if change == 'same_length_bytes':
                path.write_bytes(b'other')
            elif change == 'file_replacement':
                path.unlink(); path.write_bytes(b'first')
            elif change == 'parent_replacement':
                parent.rename(tmp_path / 'moved')
                parent.mkdir(); (parent / 'file').write_bytes(b'first')
            else:
                (tmp_path / 'alias').hardlink_to(path)
        return raw

    monkeypatch.setattr(os, 'read', racing_read)
    with pytest.raises(ValueError, match='changed during read'):
        entry.read_regular(path)


def test_directory_swap_to_symlink_during_open_is_rejected(tmp_path, monkeypatch):
    parent = tmp_path / 'directory'; parent.mkdir()
    (parent / 'file').write_bytes(b'bytes')
    original_open = os.open

    def racing_open(path, flags, *args, **kwargs):
        if path == 'directory' and kwargs.get('dir_fd') is not None:
            moved = tmp_path / 'moved'
            parent.rename(moved); parent.symlink_to(moved, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', racing_open)
    with pytest.raises(OSError):
        entry.read_regular(parent / 'file')


@pytest.mark.parametrize('limit', [True, -1, 1.0, '10'])
def test_read_regular_requires_integer_limit(tmp_path, limit):
    with pytest.raises(ValueError, match='integer byte limit'):
        entry.read_regular(tmp_path / 'unused', limit)


@pytest.mark.parametrize('status', ['closed', 'incomplete', 'rejected'])
def test_cli_exit_and_goal_status(monkeypatch, capsys, status):
    monkeypatch.setattr(sys, 'argv', ['organon-t-native', 'run', '/synthetic/plan', '--plan-sha256', 'a' * 64])
    calls = []

    def synthetic_launch(plan, expected, operation):
        calls.append((plan, expected, operation))
        return {'status': status, 'goal_achieved': True, 'synthetic': True}

    monkeypatch.setattr(entry, 'launch', synthetic_launch)
    assert entry.main() == (0 if status == 'closed' else 2)
    value = json.loads(capsys.readouterr().out)
    assert value['goal_achieved'] is (status == 'closed')
    assert calls == [(Path('/synthetic/plan'), 'a' * 64, 'run')]


@pytest.mark.parametrize('result', [[], {'status': True}, {'status': 'unknown'},
                                  {'status': 'incomplete', 'value': float('nan')}])
def test_cli_invalid_results_are_rejected_json(monkeypatch, capsys, result):
    monkeypatch.setattr(sys, 'argv', ['organon-t-native', 'report', '/synthetic/plan', '--plan-sha256', 'a' * 64])
    monkeypatch.setattr(entry, 'launch', lambda *args: result)
    assert entry.main() == 2
    captured = capsys.readouterr()
    assert not captured.out
    value = json.loads(captured.err)
    assert value['status'] == 'rejected' and value['goal_achieved'] is False
