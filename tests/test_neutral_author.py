"""Explicit neutral response grammar fixtures, no providers or method outcomes."""
import copy
import json

import pytest

from scripts.controller_native_role import (NativeRoleError, author_format_from_request,
    response_contract_from_request, render_prompt, validate_result)
from specorganon.author_contract import AUTHOR_FORMATS, typed_author_manifest
from specorganon.native_response_contract import response_schema, validate_response_schema
from specorganon.neutral_author import neutral_author_content
from specorganon.software_controller import Controller, ControllerError


def content():
    return {'schema': 1, 'files': {'program.py': 'print("synthetic")\n'},
            'documents': {'notes/criteria.md': 'Criteria before any execution; synthetic fixture'},
            'reason': 'Synthetic grammar control only'}


def request():
    return {'schema': 1, 'role': 'author', 'role_instructions': 'Synthetic neutral author syntax only',
            'documents': {'action.txt': 'author',
                          'author-response-format.json': json.dumps({'schema': 1, 'format': 'files-v1'})}}


def test_explicit_neutral_route_keeps_content_exact_and_does_not_author_steps():
    value = content(); original = copy.deepcopy(value)
    accepted = neutral_author_content(value)
    validate_result(value, 'author', author_format='files-v1')
    validate_response_schema(value, response_contract_from_request(request()))
    assert accepted == original == value and 'manifest' not in accepted and 'items' not in accepted
    accepted['documents']['notes/criteria.md'] = 'changed clone'
    assert value == original


@pytest.mark.parametrize('group', ['files', 'documents'])
def test_neutral_route_accepts_single_nonempty_group_without_filling_the_other(group):
    value = content(); value['documents' if group == 'files' else 'files'] = {}
    assert neutral_author_content(value) == value
    validate_response_schema(value, response_schema('author', author_format='files-v1'))


@pytest.mark.parametrize('fault', ['bool_schema','empty','missing_documents','items','manifest','receipt','passed',
    'blank_reason','object_text','bad_map','absolute','parent','hidden','backslash','newline','long_name'])
def test_neutral_route_refuses_ambiguity_or_authority_without_repair(fault):
    value = content()
    if fault == 'bool_schema': value['schema'] = True
    if fault == 'empty': value['files'] = {}; value['documents'] = {}
    if fault == 'missing_documents': del value['documents']
    if fault in {'items','manifest','receipt','passed'}: value[fault] = [] if fault == 'items' else {}
    if fault == 'blank_reason': value['reason'] = ' \n\t '
    if fault == 'object_text': value['files']['program.py'] = {'text': 'unchecked object'}
    if fault == 'bad_map': value['documents'] = []
    if fault in {'absolute','parent','hidden','backslash','newline','long_name'}:
        name = {'absolute':'/outside.py','parent':'../outside.py','hidden':'.hidden.py',
                'backslash':'x\\outside.py','newline':'outside.py\n','long_name':'x'*201}[fault]
        value['files'] = {name: 'synthetic'}
    original = copy.deepcopy(value)
    with pytest.raises(ValueError): neutral_author_content(value)
    with pytest.raises(ValueError): validate_response_schema(value, response_schema('author', author_format='files-v1'))
    with pytest.raises(NativeRoleError): validate_result(value, 'author', author_format='files-v1')
    assert value == original


@pytest.mark.parametrize('declaration', [None, {'schema':1,'format':'manifest-v1'},
    {'schema':True,'format':'files-v1'}, {'schema':1,'format':'files-v1','extra':True}, []])
def test_neutral_route_cannot_be_inferred_from_a_legacy_or_malformed_declaration(declaration):
    r = request()
    if declaration is None:
        del r['documents']['author-response-format.json']
        assert author_format_from_request(r) == 'manifest-v1'
        with pytest.raises(ValueError): validate_response_schema(content(), response_contract_from_request(r))
    else:
        r['documents']['author-response-format.json'] = json.dumps(declaration)
        with pytest.raises(NativeRoleError): render_prompt(json.dumps(r).encode())


def test_toolkit_controller_and_typed_assembly_do_not_acquire_neutral_engine_semantics(tmp_path):
    assert AUTHOR_FORMATS == {'manifest-v1','items-v1'}
    with pytest.raises(ValueError): typed_author_manifest(content())
    with pytest.raises(ControllerError, match='unsupported author format'):
        Controller(tmp_path/'case',tmp_path/'run',None,contract='fixture',mandate='fixture',author_format='files-v1')
    assert not (tmp_path/'case').exists() and not (tmp_path/'run').exists()


def test_neutral_author_declaration_is_not_valid_for_a_reviewer_or_an_approval():
    r = request(); r['role'] = 'review'; r['documents']['action.txt'] = 'review'
    with pytest.raises(NativeRoleError): render_prompt(json.dumps(r).encode())
    r = request(); r['documents']['action.txt'] = 'approval'
    with pytest.raises(NativeRoleError): render_prompt(json.dumps(r).encode())


def test_prompt_declares_neutral_syntax_in_the_original_single_turn_only():
    _, prompt = render_prompt(json.dumps(request()).encode())
    assert 'OUTPUT CONTRACT' in prompt and '"documents"' in prompt
    assert '"steps"' not in prompt and '"items"' not in prompt
