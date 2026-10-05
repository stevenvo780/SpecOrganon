"""New real Docker mechanism controls; no study delivery or native model call."""
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.software_comparison_v1.reserved import docker_evaluator as D
from specorganon.role_jobs import _json, _write, digest


def main(root):
    root = Path(root)
    if root.exists():
        raise ValueError('new control root required; do not replace closed or uncertain executions')
    root.mkdir(mode=0o700)
    image = 'sha256:62ad297a92f147e335bc026906f98ead9807edfea0a96337defd926801b1ec41'
    ids = ['new-control.1.0', 'nuevo-١', '../outside', '/absolute', 'control-é', 'control-e\u0301']
    files = {'treemap.py': 'print(\'{"files":[],"total_bytes":0,"symlinks":[]}\')\n'}
    policy = {'schema': 1, 'classification': 'fixed-output transport control, not task solution',
              'image': image, 'logical_ids': ids, 'files': files,
              'controller_sha256': digest(Path(D.__file__).read_bytes()),
              'native_model_calls': 0, 'study_cases_rerun': 0}
    _write(root / 'control-registration.json', policy)
    runner = D.ReservedDocker(root / 'ordinary', image)
    results = []
    first_case = None
    first_receipt = None
    for logical_id in ids:
        case = {'id': logical_id, 'task': 'treemap', 'group': 'new-transport-control',
                'entries': [], 'argv': ['--root', '/fixture/root'], 'stdin_hex': '',
                'expected': {'files': [], 'total_bytes': 0, 'symlinks': []}}
        result = runner.run(logical_id, case, files)
        assert result['verdict']['status'] == 'pass'
        assert result['request']['logical_id'] == logical_id
        assert result['request']['opaque_id'] == D.invocation_identity(logical_id, case)
        assert not result['reused_closed_receipt']
        results.append(result)
        if first_case is None:
            first_case = case
            first_receipt = Path(result['receipt_ref']).read_bytes()
    replay = runner.run(first_case['id'], first_case, files)
    assert replay['reused_closed_receipt']
    assert Path(replay['receipt_ref']).read_bytes() == first_receipt
    changed = copy.deepcopy(first_case)
    changed['expected']['total_bytes'] = 1
    try:
        runner.run(changed['id'], changed, files)
    except D.EvaluationError as error:
        assert 'changed' in str(error)
    else:
        raise AssertionError('changed recipe must not launch replacement')
    count = len(list((runner.root / 'invocations').iterdir()))
    assert count == len(ids)
    original_identity = D.invocation_identity
    collision_runner = D.ReservedDocker(root / 'simulated-collision', image)
    D.invocation_identity = lambda logical_id, case: 'f' * 64
    try:
        collision = {**first_case, 'id': 'collision-left'}
        collision_result = collision_runner.run(collision['id'], collision, files)
        assert collision_result['verdict']['status'] == 'pass'
        other = {**collision, 'id': 'collision-right'}
        try:
            collision_runner.run(other['id'], other, files)
        except D.EvaluationError as error:
            assert 'changed' in str(error)
        else:
            raise AssertionError('simulated collision must fail before replacement')
        assert len(list((collision_runner.root / 'invocations').iterdir())) == 1
    finally:
        D.invocation_identity = original_identity
    summary = {'schema': 1, 'classification': policy['classification'],
               'ordinary_actual_subjects': len(ids), 'simulated_collision_actual_subjects': 1,
               'same_closed_receipt_reused': True, 'recipe_mutation_rejected': True,
               'simulated_collision_rejected': True, 'ordinary_results': results,
               'collision_result': collision_result, 'native_model_calls': 0,
               'study_cases_rerun': 0, 'new_nine_phase_delivery': False}
    _write(root / 'summary.json', summary)
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in {'ordinary_results', 'collision_result'}}, indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
