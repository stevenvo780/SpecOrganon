"""Read-only pre-registration admission checks; no case or model calls."""
import hashlib
from pathlib import Path

import pytest

from scripts.lotledger_delivery import RegistrationError, verify_registration, verify_runtime_sources


SOURCE = Path(__file__).resolve().parents[1]


def bindings():
    return {str(p.relative_to(SOURCE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('src/specorganon', 'scripts', 'experiments')
            for p in (SOURCE / folder).rglob('*.py')}


def test_actual_loaded_source_modules_match_new_driver_checkout():
    verify_runtime_sources(SOURCE, bindings())


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
