"""Read closed native packets without rerunning models, subjects or ledgers."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from specorganon.author_contract import manifest_error_detail
from specorganon.runner import _manifest_steps


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(registration_path):
    registration = json.loads(registration_path.read_text())
    root = Path(registration['run_root'])
    progress_path = root / 'progress.json'
    progress = json.loads(progress_path.read_text())
    cells = {c['id']: c for c in registration['cells']}
    records = []
    for identity, history in sorted(progress['steps'].items()):
        failure = history[-1].get('failure', {}).get('reason', '')
        if failure not in {'invalid author manifest', 'author needs bounded substantive puts'}:
            continue
        cell = root / 'cells' / identity
        controller_progress = cell / 'generation/controller/progress.json'
        if controller_progress.exists():
            source = controller_progress
            pending = json.loads(source.read_text())['pending']
            response = pending['packet']['result']
            phase = pending['phase']
        else:
            source = sorted((cell / 'generation').glob('*-packet.json'))[-1]
            response = json.loads(source.read_text())['result']
            phase = source.name.split('-')[2]
        try:
            steps = _manifest_steps(response['manifest'])
        except ValueError as error:
            cause = manifest_error_detail(error)
        else:
            assert failure == 'author needs bounded substantive puts'
            cause = 'empty_steps' if not steps else 'too_many_steps'
        records.append({
            'cell': identity, 'method': cells[identity]['method'], 'phase': phase,
            'registered_stop': failure, 'structural_cause': cause,
            'packet_source': str(source), 'packet_source_sha256': sha(source),
            'steps': len(response['manifest'].get('steps', [])),
        })
    return {
        'schema': 1, 'scope': 'read-only structural diagnosis of closed recorded packets',
        'registration': str(registration_path), 'registration_sha256': sha(registration_path),
        'progress_sha256': sha(progress_path), 'records': records,
        'cause_counts': dict(Counter(row['structural_cause'] for row in records)),
        'new_model_calls': 0, 'new_subjects': 0, 'packets_reapplied': 0,
        'effect_of_new_guidance_measured': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('registration', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = inspect(args.registration)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'records': len(result['records']), 'causes': result['cause_counts'],
                      'new_model_calls': 0, 'new_subjects': 0}))
