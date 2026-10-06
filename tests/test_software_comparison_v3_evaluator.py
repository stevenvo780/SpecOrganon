"""Synthetic evaluator/oracle controls, never native comparison deliveries."""
import json
import math
import sys

import pytest

from experiments.software_comparison_v3.reserved import (
    ERROR, TASK_COUNTS, TASK_FILES, coprime_denominators, decimal_text, judge, recipes,
)
from experiments.software_comparison_v3.subjects import HELD_OPEN_WRAPPER, subject_command


def result(stdout=b'', stderr=b'', exit_code=0, **extra):
    return {'stdout': stdout, 'stderr': stderr, 'exit_code': exit_code,
            'timed_out': False, 'truncated_streams': [], **extra}


def fixture_output(recipe):
    target = recipe['expected']
    if target is None:
        return result(stderr=ERROR, exit_code=2)
    if recipe['task'] == 'fractionmix':
        text = ('{"numerator":' + target['numerator_decimal'] + ',"denominator":'
                + target['denominator_decimal'] + ',"term_count":' + str(target['term_count']) + '}\n')
        return result(text.encode())
    return result(json.dumps(target, ensure_ascii=False, separators=(',', ':')).encode() + b'\n')


def test_recipe_population_is_finite_preselected_and_has_no_delivery_output():
    rows = recipes()
    assert len(rows) == 250 and len({r['id'] for r in rows}) == 250
    for task, count in TASK_COUNTS.items():
        chosen = [r for r in rows if r['task'] == task]
        assert len(chosen) == count and sum(r['public'] for r in chosen) == 2
        assert sum(r['stdin_mode'] == 'held_open' for r in chosen) == 1
        for row in chosen:
            raw = bytes.fromhex(row['stdin_hex'])
            assert len(raw) <= 65537
            if row['expected'] is not None:
                assert len(raw) <= 65536 and not row['argv']
            assert subject_command(row)[-1] if row['argv'] else True


def test_invalid_utf8_probe_isolates_lossy_decoder_instead_of_empty_json_failure():
    for task in TASK_FILES:
        row = next(r for r in recipes(task) if r['id'].endswith('-format-bad-utf8'))
        raw = bytes.fromhex(row['stdin_hex'])
        assert row['expected'] is None and raw.startswith(b'\xff{')
        with pytest.raises(UnicodeDecodeError): raw.decode('utf-8', 'strict')
        # A decoder silently ignoring invalid bytes reaches a VALID JSON
        # document; the probe must reject that otherwise-successful route.
        assert type(json.loads(raw.decode('utf-8', 'ignore'))) is dict


@pytest.mark.parametrize('task', TASK_FILES)
def test_all_oracle_fixtures_parse_including_types_and_large_integers(task):
    limit = sys.get_int_max_str_digits()
    for row in recipes(task):
        assert judge(row, fixture_output(row))['status'] == 'pass', row['id']
    assert sys.get_int_max_str_digits() == limit


def test_fraction_public_anchors_are_not_just_self_generated_oracle_parsing():
    pub = [r for r in recipes('fractionmix') if r['public']]
    assert pub[0]['expected'] == {'numerator_decimal': '5', 'denominator_decimal': '6', 'term_count': 2}
    assert pub[1]['expected'] == {'numerator_decimal': '0', 'denominator_decimal': '1', 'term_count': 2}


def test_large_fraction_oracle_agrees_with_independent_common_denominator():
    ds = coprime_denominators()
    denominator = math.prod(ds)
    numerator = sum(denominator // d for d in ds)
    assert math.gcd(numerator, denominator) == 1
    row = next(r for r in recipes('fractionmix') if '7331-digit' in r['id'])
    assert row['expected']['numerator_decimal'] == decimal_text(numerator)
    assert row['expected']['denominator_decimal'] == decimal_text(denominator)
    assert len(row['expected']['denominator_decimal']) == 7331
    bad = fixture_output(row)
    bad['stdout'] = bad['stdout'].replace(b'"numerator":', b'"numerator":"', 1).replace(b',"denominator":', b'","denominator":', 1)
    assert judge(row, bad)['status'] == 'fail'


@pytest.mark.parametrize('task', TASK_FILES)
@pytest.mark.parametrize('mutation', ['prefix', 'suffix', 'double_LF', 'BOM', 'stderr', 'exit', 'timeout', 'truncated', 'wrong-value'])
def test_captured_success_contract_rejects_actual_stream_and_exit_mutations(task, mutation):
    row = next(r for r in recipes(task) if r['public'])
    actual = fixture_output(row)
    if mutation == 'prefix': actual['stdout'] = b' ' + actual['stdout']
    elif mutation == 'suffix': actual['stdout'] += b' '
    elif mutation == 'double_LF': actual['stdout'] += b'\n'
    elif mutation == 'BOM': actual['stdout'] = b'\xef\xbb\xbf' + actual['stdout']
    elif mutation == 'stderr': actual['stderr'] = b'warning'
    elif mutation == 'exit': actual['exit_code'] = 1
    elif mutation == 'timeout': actual['timed_out'] = True
    elif mutation == 'truncated': actual['truncated_streams'] = ['stdout']
    else: actual['stdout'] = b'{}\n'
    assert judge(row, actual)['status'] == 'fail'


@pytest.mark.parametrize('raw', [b'{"numerator":true,"denominator":6,"term_count":2}\n',
    b'{"numerator":5.0,"denominator":6,"term_count":2}\n',
    b'{"numerator":"5","denominator":6,"term_count":2}\n',
    b'{"numerator":5,"denominator":6,"term_count":2,"term_count":2}\n',
    b'{"numerator":NaN,"denominator":6,"term_count":2}\n',
    b'{"numerator":Infinity,"denominator":6,"term_count":2}\n',
    b'{"numerator":5,"denominator":6,"term_count":2}{}\n'])
def test_output_integer_type_and_duplicate_nonfinite_json_guards(raw):
    row = next(r for r in recipes('fractionmix') if r['public'])
    assert judge(row, result(raw))['status'] == 'fail'


@pytest.mark.parametrize('task', TASK_FILES)
def test_pretty_print_and_key_order_are_allowed_without_coercion(task):
    row = next(r for r in recipes(task) if r['public'])
    if task == 'fractionmix':
        raw = b'{\n "term_count": 2,\n "denominator": 6,\n "numerator": 5\n}\n'
    else:
        raw = json.dumps(row['expected'], indent=2, ensure_ascii=False).encode() + b'\n'
    assert judge(row, result(raw))['status'] == 'pass'


@pytest.mark.parametrize('task', TASK_FILES)
def test_invalid_input_requires_exact_error_not_merely_exit_two(task):
    row = next(r for r in recipes(task) if r['expected'] is None)
    assert judge(row, result(stderr=ERROR, exit_code=2))['status'] == 'pass'
    for wrong in [result(stderr=ERROR, exit_code=0), result(stdout=b'{}\n', stderr=ERROR, exit_code=2),
                  result(stderr=b'invalid_input\n', exit_code=2), result(stderr=ERROR + b'\n', exit_code=2)]:
        assert judge(row, wrong)['status'] == 'fail'
    assert judge(row, result(infrastructure_error='daemon inaccessible'))['status'] == 'inconclusive'


def test_order_relations_and_domain_specific_public_anchors():
    rows = {r['id']: r for r in recipes()}
    for row in rows.values():
        if row['relation']:
            assert row['expected'] == rows[row['relation']['same_output_as']]['expected']
    policy = rows['policypick-semantics-public-tie']
    assert policy['expected'] == {'decisions': [{'id': 'yes', 'rule': 'A'}, {'id': 'no', 'rule': None}]}
    patch = rows['listpatch-semantics-public-sequence']
    assert patch['expected'] == {'items': [9, 15], 'applied': 3}


def test_held_open_command_uses_registered_task_child_and_keeps_observer_separate():
    for task, filename in TASK_FILES.items():
        row = next(r for r in recipes(task) if r['stdin_mode'] == 'held_open')
        argv = subject_command(row)
        assert argv[:3] == ['/usr/bin/timeout', '--signal=KILL', '3s']
        assert HELD_OPEN_WRAPPER in argv
        assert argv[-6:] == ['/opt/specorganon/venv/bin/python', '-E', '-s', '-B', '/input/delivery/' + filename, '--help']
        assert '/observer/stdin-observer.json' in HELD_OPEN_WRAPPER
        assert not row['stdin_hex']


def test_persistent_subject_policy_binds_the_actual_oracle_code(tmp_path, monkeypatch):
    from experiments.software_comparison_v3 import reserved
    from experiments.software_comparison_v3.subjects import Subjects, SubjectError
    from specorganon.role_jobs import _json
    from specorganon.docker_roles import DockerRoles
    from pathlib import Path
    image = 'sha256:' + '1' * 64
    # This is a hermetic policy-binding fixture, not a real-image availability
    # assertion. The separate Docker preflight uses the actual immutable image.
    monkeypatch.setattr(DockerRoles, '_image', staticmethod(lambda ref: ref))
    subject = Subjects(tmp_path / 'subjects', image, 'fractionmix')
    before = (subject.root / 'policy.json').read_bytes()
    changed = tmp_path / 'changed-oracle.py'
    changed.write_bytes(Path(reserved.__file__).read_bytes() + b'\n# Synthetic oracle divergence\n')
    monkeypatch.setattr(reserved, '__file__', str(changed))
    with pytest.raises(SubjectError, match='policy changed'):
        Subjects(subject.root, image, 'fractionmix')
    assert (subject.root / 'policy.json').read_bytes() == before
    assert _json(subject.root / 'policy.json')['max_subjects'] == 84
