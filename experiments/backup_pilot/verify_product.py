#!/usr/bin/env python3
"""Verify the unchanged selected product; never replace cohort results."""
import base64
import json
from pathlib import Path

import clean_runtime
import run_pilot

BASE = Path(__file__).resolve().parent


def main():
    if not (BASE / 'runs/complete.json').is_file():
        raise SystemExit('Campaign incomplete')
    manifest = json.loads((BASE / 'frozen/manifest.json').read_text())
    run_pilot.check_freeze(manifest)
    provenance = json.loads((BASE / 'product/provenance.json').read_text())
    product = BASE / 'product'
    for source in provenance['files']:
        if run_pilot.digest(Path(source['source'])) != source['sha256'] or run_pilot.digest(product / source['delivered']) != source['sha256']:
            raise SystemExit('Product source changed; explicit disposition required')
    review = json.loads((BASE / 'analysis/manual-review/selected-source.json').read_text())
    if review.get('dependency_policy_selected_source_pass') is not True or review['source_sha256'] != run_pilot.digest(product / 'backup.py'):
        raise SystemExit('Matching selected-source review required')
    build = json.loads((BASE / 'development/delivery-build.json').read_text())
    image = clean_runtime.check_image(build['image_id'])
    output = BASE / 'analysis/product-verification'
    output.mkdir(exist_ok=True)
    evaluations = []
    for variant in ('V1', 'V2', 'V3'):
        original = next(row for row in manifest['schedule'] if row['variant'] == variant and row['repeat'] == 1)
        row = {**original, 'id': 'selected-' + variant}
        directory = output / variant
        directory.mkdir(exist_ok=True)
        expected = clean_runtime.argv(product, row, 2, image)
        receipt = run_pilot.once(directory / 'receipt.json', lambda: clean_runtime.observe(product, row, 2, image, directory))
        if receipt['argv'] != expected or run_pilot.digest(directory / 'evaluation.jsonl') != receipt['stdout_sha256'] or run_pilot.digest(directory / 'evaluation.stderr') != receipt['stderr_sha256']:
            raise SystemExit('Product verification receipt mismatch')
        status, grade, error = clean_runtime.classify(directory, receipt, 2)
        if status != 'evaluated':
            raise SystemExit('Product observer failure: ' + str(error))
        run_pilot.save(directory / 'evaluation.json', grade)
        streams = directory / 'evaluation-streams'
        streams.mkdir(exist_ok=True)
        for stream in grade['output_streams']:
            (streams / stream['name']).write_bytes(base64.b64decode(stream['base64'], validate=True))
        run_pilot.save(streams / 'index.json', [{k: v for k, v in item.items() if k != 'base64'} for item in grade['output_streams']])
        evaluations.append({'variant': variant, 'seed': row['workload_seed'],
                            'passed': grade['checks_passed'], 'total': grade['checks_total'],
                            'critical': grade['critical_failures'], 'inconclusive': grade['inconclusive'],
                            'receipt': str(directory / 'receipt.json')})
    own_checks = []
    for filename in ('test_backup.py', 'examples.py'):
        name = 'backup-selected-' + ('tests' if filename.startswith('test') else 'examples')
        argv = ['docker', 'run', '--rm', '--name', name, '--network', 'none', '--read-only',
                '--user', '1000:1000', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                '--memory', '768m', '--cpus', '1', '--pids-limit', '64',
                '--tmpfs', '/trial:rw,size=512m,mode=0755,uid=1000,gid=1000',
                '--tmpfs', '/tmp:rw,size=128m,mode=1777',
                '--mount', f'type=bind,src={product},dst=/trial/solution,readonly',
                '--entrypoint', '/usr/local/bin/python', manifest['images']['control'],
                '-E', '-s', '-S', '-B', '/trial/solution/' + filename]
        path = output / ('tests' if filename.startswith('test') else 'examples')
        receipt = run_pilot.once(path.with_suffix('.receipt.json'), lambda: run_pilot.command(argv, path, 120, container=name))
        if receipt['argv'] != argv or run_pilot.digest(path.with_suffix('.jsonl')) != receipt['stdout_sha256'] or run_pilot.digest(path.with_suffix('.stderr')) != receipt['stderr_sha256']:
            raise SystemExit('Own-check receipt mismatch')
        own_checks.append({'file': filename, 'exit_code': receipt['exit_code'], 'timed_out': receipt['timed_out'], 'receipt': str(path.with_suffix('.receipt.json'))})
    passed = all(row['passed'] == row['total'] == 22 and not row['critical'] and not row['inconclusive'] for row in evaluations) and all(row['exit_code'] == 0 and not row['timed_out'] for row in own_checks)
    result = {'kind': 'post-selection engineering verification; not new independent pilot runs',
              'selected_run': provenance['selected_run'], 'source_sha256': run_pilot.digest(product / 'backup.py'),
              'image_id': image, 'evaluations': evaluations, 'own_checks': own_checks, 'passed': passed,
              'primary_results_modified': False, 'limitations': ['Uses existing reserved case families and seeds after selection; not an unseen confirmatory holdout.']}
    run_pilot.save(output / 'report.json', result)
    if not passed:
        raise SystemExit('Product verification failed; preserve observations, no favorable automatic retry')
    provenance['status'] = 'verified unchanged in three variants and isolated own checks'
    run_pilot.save(product / 'provenance.json', provenance)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
