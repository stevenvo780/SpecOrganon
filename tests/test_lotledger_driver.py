"""Read-only pre-registration admission checks; no case or model calls."""
import hashlib
import ast
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
    assert 'scripts/analyze_bread_survey.py' not in names


def test_binding_cannot_omit_or_change_actual_loaded_core_module():
    for mode in ('missing', 'wrong'):
        checksums = bindings()
        if mode == 'missing':
            del checksums['src/specorganon/engine.py']
        else:
            checksums['src/specorganon/engine.py'] = '0' * 64
        with pytest.raises(RegistrationError, match='runtime module is not source-bound'):
            verify_runtime_sources(SOURCE, checksums)


def test_old_closed_registration_never_admits_new_identity_or_writes_history():
    old = Path('/home/stev/.codex/worktrees/prospective-software-repairs/SpecOrganon')
    registration = old / 'experiments/csvshape_delivery_v1/frozen/registration.json'
    ledger = old / 'cases/csvshape_v1/organon.json'
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
