"""Prepare a new ten-position T development registration; no model/Docker calls."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from specorganon import __version__
from specorganon.common_review import checklist
from specorganon.neutral_controller import LIMITS
from specorganon.role_jobs import _safe, _read, canonical, digest
from specorganon.t_native_pilot import (CLASSIFICATION, PROTOCOL, PROTOCOL_FILE, MANDATE,
    ATTEMPTS, SCOPE, AUTHOR_FORMAT, required_sources, task_policy, validate_registration)


def prepare(source, runtime, pilot_id, transport, capacity_evidence):
    source = _safe(source); runtime = _safe(runtime)
    r = {'schema': 1, 'classification': CLASSIFICATION, 'protocol': PROTOCOL, 'id': pilot_id,
        'registered_at': datetime.now(timezone.utc).isoformat(), 'candidate_version': __version__,
        'source_root': str(source), 'source_commit': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(),
        'source_sha256': {n: digest(_read(source / n)) for n in sorted(required_sources(source))},
        'run_root': str(runtime), 'fixture_mode': False, 'automatic_replacement': False,
        'controller_limits': LIMITS, 'author_format': AUTHOR_FORMAT, 'transport': transport,
        'public_catalog': 'experiments/software_comparison_v3/public-models.json', 'seccomp': 'docker/codex/seccomp-codex.json',
        'mandate': MANDATE, 'protocol_file': PROTOCOL_FILE, 'tasks': task_policy(), 'attempts': ATTEMPTS,
        'scope': SCOPE, 'H_checklist': checklist('T')['H'], 'capacity_evidence': capacity_evidence}
    return validate_registration(r)


def main():
    from specorganon.role_jobs import _json
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('plan', type=Path)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--pilot-id', required=True)
    p.add_argument('--transport-json', type=Path, required=True)
    p.add_argument('--capacity-json', type=Path, required=True)
    a = p.parse_args()
    if a.plan.exists() or a.run_root.exists(): raise ValueError('fresh registration/runtime required; no replacement')
    r = prepare(a.source_root, a.run_root, a.pilot_id, _json(a.transport_json), _json(a.capacity_json))
    a.plan.parent.mkdir(parents=True, exist_ok=True); raw = canonical(r)
    # O_EXCL consumes publication once, including a crash with partial bytes.
    # A partial registration remains rejected, never overwritten as a recovery.
    import os
    from specorganon.role_jobs import _parent
    parent, name = _parent(a.plan.absolute())
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.fsync(parent)
    finally: os.close(parent)
    print(canonical({'plan': str(a.plan.absolute()), 'sha256': digest(raw), 'planned_attempts': 10,
                     'model_calls': 0, 'development_qualification': False, 'goal_achieved': False}).decode())


if __name__ == '__main__': main()
