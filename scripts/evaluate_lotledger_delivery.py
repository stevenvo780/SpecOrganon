"""Postclosure reserved LotLedger evaluation; never sends results back to authors."""
import argparse
import json
from pathlib import Path

from experiments.lotledger_delivery_v1.reserved import recipes
from experiments.lotledger_delivery_v1.subjects import Subjects, SubjectError
from scripts.lotledger_delivery import verify_registration, run_lock, RegistrationError
from specorganon.role_jobs import JobError, _json, _write, _read, canonical, digest
from specorganon.software_controller import safe_file, encoded_contribution


def evaluate(registration):
    value, registration_sha256 = verify_registration(registration)
    root = Path(value['run_root'])
    with run_lock(root):
        if not (root / 'terminal.json').exists(): raise RegistrationError('generation must close before reserved evaluation')
        terminal = _json(root / 'terminal.json')
        folder = root / 'controller/delivery'; files = {}
        if folder.exists():
            for p in sorted(folder.rglob('*')):
                if p.is_symlink() or not (p.is_file() or p.is_dir()): raise SubjectError('nonregular delivery entry')
                if p.is_file():
                    name = str(p.relative_to(folder)); safe_file(name)
                    files[name] = _read(p, 20000).decode('utf-8')
        path = root / 'reserved-evaluation.json'
        binding = {'registration_sha256': registration_sha256, 'delivery_sha256': digest(canonical(files)),
                   'generation_terminal_sha256': digest(canonical(terminal))}
        if path.exists():
            result = _json(path)
            if result['binding'] != binding: raise SubjectError('closed evaluation delivery changed')
            return result
        # Seal the one final snapshot before any subject invocation.
        seal = root / 'evaluation-binding.json'
        if seal.exists() and _json(seal) != binding: raise SubjectError('partial evaluation snapshot changed')
        if not seal.exists(): _write(seal, binding)
        matrix = recipes(); rows = []
        invalid = ('programme not delivered' if 'lotledger.py' not in files else
                   'delivery envelope exceeded' if encoded_contribution(files) > 20000 else None)
        subjects = Subjects(root / 'reserved-subjects', value['images']['test']) if invalid is None else None
        for recipe in matrix:
            if invalid is not None:
                row = {'id': recipe['id'], 'public': recipe['public'], 'status': 'fail', 'reason': invalid, 'receipt_ref': None}
            else:
                try: row = subjects.run(recipe['id'], recipe, files)
                except (SubjectError, JobError, OSError, ValueError) as exc:
                    row = {'id': recipe['id'], 'public': recipe['public'], 'status': 'inconclusive', 'reason': str(exc)}
            rows.append(row)
            _write(root / 'last-reserved-progress.json', {'binding': binding, 'rows': rows, 'complete': False})
        counts = {s: sum(r['status'] == s for r in rows) for s in ('pass', 'fail', 'inconclusive')}
        audit_path = root / 'final-doc-method-audit.json'
        audit = _json(audit_path) if audit_path.exists() else None
        audited = bool(audit and audit.get('delivery_sha256') == binding['delivery_sha256']
                       and audit.get('documentation_passed') is True and audit.get('method_passed') is True)
        result = {'schema': 1, 'binding': binding, 'rows': rows, 'counts': counts,
                  'contract_passed': counts['pass'] == len(matrix), 'denominator': len(matrix),
                  'nine_phase_package_gate': terminal['status'] == 'package_gate_passed',
                  'documentation_method_audit_passed': audited,
                  'engineering_verdict': ('completed_technical' if terminal['status'] == 'package_gate_passed'
                      and audited and counts['pass'] == len(matrix) else 'infra_inconclusive' if counts['inconclusive']
                      else 'delivery_failed'), 'method_superiority': 'not demonstrated',
                  'token_usage': None, 'monetary_cost': None, 'authors_received_reserved_results': False}
        _write(path, result); return result


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--registration', required=True)
    args = parser.parse_args()
    try: result = evaluate(args.registration)
    except (RegistrationError, SubjectError, JobError, OSError, ValueError) as exc:
        print(json.dumps({'status': 'evaluation_rejected', 'reason': str(exc)})); return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0


if __name__ == '__main__': raise SystemExit(main())
