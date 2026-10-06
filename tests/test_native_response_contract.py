"""Synthetic syntax/transport controls; not native efficacy or approval."""
import copy
import json

import pytest

from scripts.controller_native_role import NativeRoleError, native_argv, response_json, render_prompt
from specorganon.native_response_contract import response_schema, validate_response_schema


def review(**extra):
    return {'schema': 1, 'verdict': 'reject', 'reason': 'No measured receipt supplied',
            'findings': [{'artifact': 'test', 'problem': 'receipt absent'}],
            'tests_executed': False, **extra}


def author(fmt):
    item = {'id': 'p1', 'kind': 'problem', 'text': 'Synthetic fixture only', 'refs': [], 'data': {}}
    value = {'schema': 1, 'files': {}, 'reason': 'Synthetic grammar control only'}
    if fmt == 'items-v1': value['items'] = [item]
    else: value['manifest'] = {'schema': 1, 'steps': [{'op': 'put', **item}]}
    return value


@pytest.mark.parametrize('verdict', ['accept', 'reject', 'inconclusive'])
@pytest.mark.parametrize('conformity', [True, False])
def test_schema_does_not_predetermine_approval_or_judgment(verdict, conformity):
    value = review(mandate_conformity=conformity, approval_targets=[])
    value['verdict'] = verdict
    validate_response_schema(value, response_schema('review', approval=True))


@pytest.mark.parametrize('fault', ['missing_false', 'false_zero', 'true', 'blank_reason', 'extra',
                                 'bad_verdict', 'empty_finding', 'string_finding', 'approval_on_review'])
def test_schema_refuses_invalid_text_only_judgments(fault):
    value = review()
    if fault == 'missing_false': value.pop('tests_executed')
    elif fault == 'false_zero': value['tests_executed'] = 0
    elif fault == 'true': value['tests_executed'] = True
    elif fault == 'blank_reason': value['reason'] = ' \n\t '
    elif fault == 'extra': value['unexpected'] = 'unchecked extra field'
    elif fault == 'bad_verdict': value['verdict'] = 'magic'
    elif fault == 'empty_finding': value['findings'] = [{}]
    elif fault == 'string_finding': value['findings'] = ['praise']
    else: value['mandate_conformity'] = True
    original = copy.deepcopy(value)
    with pytest.raises(ValueError): validate_response_schema(value, response_schema('review'))
    assert value == original


@pytest.mark.parametrize('fmt', ['items-v1', 'manifest-v1'])
def test_author_syntax_accepts_both_routes_without_authoring_content(fmt):
    value = author(fmt); original = copy.deepcopy(value)
    validate_response_schema(value, response_schema('author', author_format=fmt))
    assert value == original


@pytest.mark.parametrize('fmt', ['items-v1', 'manifest-v1'])
@pytest.mark.parametrize('fault', ['no_items', 'unknown_kind', 'missing_data', 'duplicate_refs',
                                 'bad_id', 'blank_text', 'too_many', 'invented_receipt_root', 'wrong_file_type'])
def test_author_schema_refuses_malformed_packets_before_controller_admission(fmt, fault):
    value = author(fmt)
    items = value['items'] if fmt == 'items-v1' else value['manifest']['steps']
    if fault == 'no_items': items.clear()
    elif fault == 'unknown_kind': items[0]['kind'] = 'approval'
    elif fault == 'missing_data': items[0].pop('data')
    elif fault == 'duplicate_refs': items[0]['refs'] = ['e1', 'e1']
    elif fault == 'bad_id': items[0]['id'] = '../../bad'
    elif fault == 'blank_text': items[0]['text'] = '\t '
    elif fault == 'too_many': items.extend(copy.deepcopy(items[0]) for _ in range(32))
    elif fault == 'invented_receipt_root': value['passed'] = True
    else: value['files'] = {'program.py': ['not text']}
    with pytest.raises(ValueError): validate_response_schema(value, response_schema('author', author_format=fmt))


@pytest.mark.parametrize('role,fmt,approval', [('author','unknown',False), ('author','items-v1',True),
                                             ('review','items-v1',1), ([], 'items-v1',False)])
def test_contract_parameters_cannot_silently_choose_a_route(role,fmt,approval):
    with pytest.raises(ValueError): response_schema(role, author_format=fmt, approval=approval)


def test_gemini_schema_guidance_is_in_single_stdin_prompt_not_cli_formatter():
    request={'schema':1,'role':'review','role_instructions':'Review supplied data only',
             'documents':{'action.txt':'approval','fixture':'untrusted document marker'}}
    _, prompt=render_prompt(json.dumps(request).encode())
    assert 'mandate_conformity' in prompt and 'untrusted document marker' in prompt
    args = native_argv('gemini', 'Gemini 3.8 Flash (Medium)', prompt)
    assert prompt not in args and '--json-schema' not in args
    assert args[-3:] == ['--input-format', 'stream-json', '--print=']
    assert '--sandbox' in args and '--disable-slash-commands' in args


def test_full_local_contract_stays_strict_without_native_formatter():
    local=response_schema('review', approval=True)
    for changes in [{'schema':2},{'tests_executed':True},{'tests_executed':'false'}]:
        value=review(mandate_conformity=False,approval_targets=[],**changes)
        with pytest.raises(ValueError): validate_response_schema(value,local)


@pytest.mark.parametrize('role,action', [('author','approval'),('review','author'),('review','unknown')])
def test_role_mismatch_stops_before_native_prompt(role,action):
    request={'schema':1,'role':role,'role_instructions':'fixture','documents':{'action.txt':action}}
    with pytest.raises(NativeRoleError,match='action and role differ'):render_prompt(json.dumps(request).encode())


def test_actual_cli_formatter_streams_stay_failed_instead_of_adopting_structured_output():
    from scripts.controller_native_role import parse_gemini_stream
    from pathlib import Path
    evidence=Path('goals/method-superiority-v1/evidence/provider-json-schema-01/native-02')
    for case in ['review-missing-receipt','approval-outside-mandate','author-items']:
        with pytest.raises(NativeRoleError):parse_gemini_stream((evidence/case/'stdout.bin').read_text())


@pytest.mark.parametrize('raw', ['```json\n{}\n```', 'Before {"schema":1}',
                                '{"schema":1,"schema":1}', '{"x":NaN}',
                                '\u00a0{}\u00a0', '\u2003{}\u2003', '\v{}\v'])
def test_structured_output_does_not_enable_post_generation_repairs(raw):
    with pytest.raises(NativeRoleError): response_json(raw)


def test_standard_json_whitespace_is_valid_without_stripping_native_text():
    assert response_json(' \t\r\n{"schema":1}\n ')=={'schema':1}
