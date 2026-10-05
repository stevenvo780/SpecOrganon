"""Read-only pre-registration admission checks; no case or model calls."""
import hashlib
import ast
import datetime
import json
from pathlib import Path

import pytest

from scripts.lotledger_delivery import RegistrationError, verify_registration, verify_runtime_sources, registration_source_names


SOURCE = Path(__file__).resolve().parents[1]


def bindings():
    return {str(p.relative_to(SOURCE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('src/specorganon', 'scripts', 'experiments')
            for p in (SOURCE / folder).rglob('*.py')}


def test_actual_loaded_source_modules_match_new_driver_checkout():
    verify_runtime_sources(SOURCE, bindings())


def test_trial_freeze_covers_local_import_closure_and_loaded_modules():
    names = registration_source_names(SOURCE,
        public_catalog='experiments/lotledger_delivery_v1/public-models.json',
        public_context='experiments/lotledger_delivery_v1/public-context.txt',
        mandate='experiments/lotledger_delivery_v1/mandate.md')
    frozen = {n: hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in names}
    verify_runtime_sources(SOURCE, frozen)
    # Each local import anywhere in the registered scripts, including functions,
    # must itself be included. No executing trial dependency may be hash-only.
    for name in names:
        if not name.startswith('scripts/') or not name.endswith('.py'): continue
        for node in ast.walk(ast.parse((SOURCE/name).read_text())):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) else
                       [entry.name for entry in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                if not module or not module.startswith(('scripts.', 'experiments.')): continue
                relative = module.replace('.', '/') + '.py'
                if (SOURCE/relative).is_file(): assert relative in names
    assert 'src/specorganon/engine.py' in names
    assert 'src/specorganon/role_jobs.py' in names
    assert 'src/specorganon/docker_roles.py' in names
    assert 'tests/test_lotledger_driver.py' in names
    assert 'tests/test_lotledger_reserved.py' in names
    assert 'experiments/lotledger_delivery_v1/image-users.json' in names
    assert 'scripts/original_profile_quota.py' in names
    assert 'scripts/study_campaign.py' not in names
    assert 'scripts/software_study_harness.py' not in names
    assert 'scripts/analyze_bread_survey.py' not in names
    assert 'experiments/software_comparison_v3/protocol-draft.md' not in names
    assert 'experiments/lotledger_delivery_v1/original60_reserved.py' in names


@pytest.mark.parametrize('text', ['```json\n{}\n```', '```\n{}\n```', '{}\nCommentary', '{} {}'])
def test_native_role_rejects_fences_and_extra_text(text):
    from scripts.controller_native_role import response_json, NativeRoleError
    with pytest.raises(NativeRoleError): response_json(text)


def test_native_role_accepts_one_strict_object_only():
    from scripts.controller_native_role import response_json, NativeRoleError
    assert response_json(' \n{"value":1}\n') == {'value':1}
    with pytest.raises(NativeRoleError): response_json('[]')


def test_contract_invocation_matches_both_subject_and_native_test_transport():
    folder = SOURCE / 'experiments/lotledger_delivery_v1'
    assert '`/opt/specorganon/venv/bin/python -E -s -B /input/delivery/lotledger.py`' in (folder/'contract.md').read_text()
    tree = ast.parse((folder/'subjects.py').read_text())
    values = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value,str)}
    assert '/input/delivery/lotledger.py' in values
    assert '-w' in values and '/input/delivery' in values
    native_tree = ast.parse((SOURCE/'src/specorganon/docker_roles.py').read_text())
    assert '/input/delivery' in {node.value for node in ast.walk(native_tree) if isinstance(node, ast.Constant) and isinstance(node.value,str)}


def test_original_quota_admission_keeps_unknown_age_and_exhaustion_controls(tmp_path):
    from scripts.original_profile_quota import current_quota, CampaignPause
    captured = datetime.datetime.now(datetime.timezone.utc)
    unknown = {'status':'unknown','remaining_percent':[], 'reason':'synthetic no-poll observation'}
    row = {'schema':1, 'accounts':{'codex':'original_lab_profile','gemini':'original_primary_profile'},
           'captured_at':captured.isoformat(),'providers':{'codex':unknown,'gemini':unknown}}
    path=tmp_path/'quota.json'; path.write_text(json.dumps(row))
    assert current_quota(path, now=captured.timestamp())['capacity_guaranteed'] is False
    with pytest.raises(CampaignPause, match='older than600s'):
        current_quota(path, now=captured.timestamp()+601)
    row['providers']['gemini']={'status':'observed','remaining_percent':[99,0],
        'source':'synthetic current quota control','observed_at':captured.isoformat()}
    path.write_text(json.dumps(row))
    with pytest.raises(CampaignPause, match='quota depleted'):
        current_quota(path, now=captured.timestamp())


@pytest.mark.parametrize('key', ['public_catalog', 'public_context', 'mandate'])
def test_registration_rejects_substituted_public_paths_before_loading_packet(tmp_path, key):
    from scripts.lotledger_delivery import PUBLIC_PATHS
    value = {'schema':1, 'identity':'lotledger-delivery-v1', 'matrix_count':73,
             'registered_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'source_root':str(SOURCE), 'case':str(SOURCE/'cases/lotledger_v1'),
             'run_root':str(tmp_path/'run'),
             'routes':{'author':{'provider':'codex','model':'gpt-6.1-sol','effort':'medium'},
                       'review':{'provider':'gemini','model':'Gemini 3.8 Flash (Medium)'}},
             'profiles':{'codex_volume':'specorganon-lab_codex-home',
                         'gemini_profile':'/home/stev/.gemini','gemini_executable':'/home/stev/.local/bin/agy'},
             'limits':{'max_calls':40,'max_total_input_bytes':3145728,'max_elapsed_seconds':6000},
             'images':{}, 'source_sha256':{}, 'review':'not_created', 'review_sha256':'',
             'matrix_sha256':'', **PUBLIC_PATHS}
    value[key] = 'experiments/lotledger_delivery_v1/reserved.py'
    path=tmp_path/'registration.json'; path.write_text(json.dumps(value))
    with pytest.raises(RegistrationError, match='fixed canonical public catalog/context/mandate paths'):
        verify_registration(path)
    assert not (tmp_path/'run').exists()


def test_binding_cannot_omit_or_change_actual_loaded_core_module():
    for mode in ('missing', 'wrong'):
        checksums = bindings()
        if mode == 'missing':
            del checksums['src/specorganon/engine.py']
        else:
            checksums['src/specorganon/engine.py'] = '0' * 64
        with pytest.raises(RegistrationError, match='runtime module is not source-bound'):
            verify_runtime_sources(SOURCE, checksums)


def test_other_identity_never_admits_or_writes_synthetic_history(tmp_path):
    # Explicit synthetic negative control; actual historical preservation is
    # verified separately by the coordinator, not a dependency of unit tests.
    registration = tmp_path / 'registration.json'
    keys = {'schema', 'identity', 'registered_at', 'source_root', 'case', 'run_root',
            'source_sha256', 'images', 'routes', 'profiles', 'limits', 'public_catalog',
            'public_context', 'mandate', 'review', 'review_sha256', 'matrix_sha256', 'matrix_count'}
    value = {key: None for key in keys}
    value.update({'schema':1, 'identity':'csvshape-delivery-v1', 'matrix_count':73})
    registration.write_text(json.dumps(value))
    ledger = tmp_path / 'organon.json'
    ledger.write_bytes(b'{"schema":1,"events":[],"synthetic":true}\n')
    before = ledger.read_bytes()
    with pytest.raises(RegistrationError, match='immutable LotLedger registration schema required'):
        verify_registration(registration)
    assert ledger.read_bytes() == before


def test_new_driver_cannot_run_under_another_checkout_binding():
    with pytest.raises(RegistrationError, match='registered driver is not the executing source checkout'):
        verify_runtime_sources('/datos/workspaces/personal/SpecOrganon', bindings())


def test_public_packet_contains_only_named_public_sources():
    folder = SOURCE / 'experiments/lotledger_delivery_v1'
    packet = (folder / 'public-context.txt').read_text()
    expected_files = ('contract.md', 'protocol.md', 'public-evidence.md', 'public-sqlite-observations.json')
    assert packet == '\n\n'.join('FILE ' + n + '\n' + (folder / n).read_text()
                                   for n in expected_files) + '\n'
    assert 'FILE reserved.py' not in packet and 'stdin_hex' not in packet
    assert len(packet.encode()) <= 64000
