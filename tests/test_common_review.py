"""Bound qualitative syntax fixtures; never substantive or physical package proof."""
import copy
import json

import pytest

from scripts.controller_native_role import NativeRoleError, render_prompt, validate_result
from specorganon.common_review import BINDING_KEYS, checklist, declaration, summarize_assertions
from specorganon.native_response_contract import response_schema, validate_response_schema


def declared(method='N'):
    return {'schema':1,'format':'common-audit-v1','method':method,
            'binding':{name:'a'*64 for name in BINDING_KEYS},
            'locators':['delivery:README.md','checkpoint:0001','receipt:test-01']}


def review(method='N',status='inconclusive'):
    d=declared(method)
    return {'schema':1,'verdict':'inconclusive','reason':'Synthetic syntax only; no physical verification',
            'findings':[{'scope':'fixture only'}],'tests_executed':False,
            'audit':{'binding':d['binding'], **{group:{key:{'status':status,'reason':'Fixture point',
                'evidence':['delivery:README.md'] if status=='pass' else []} for key in points}
                for group,points in checklist(method).items()}}}


@pytest.mark.parametrize('method',['N','S','T'])
@pytest.mark.parametrize('status',['pass','fail','inconclusive'])
def test_common_schema_binds_shape_without_fixing_a_point_or_verdict(method,status):
    value=review(method,status);before=copy.deepcopy(value)
    for verdict in ('accept','reject','inconclusive'):
        value['verdict']=verdict
        validate_response_schema(value,response_schema('review',common_audit=declared(method)))
        assert summarize_assertions(value,declared(method))['common_H_required'] is False
    assert value['audit']==before['audit']


def test_same_D_G_accept_free_prose_locators_without_SDD_or_T_names():
    assert checklist('N')['D']==checklist('S')['D']==checklist('T')['D']
    assert checklist('N')['G']==checklist('S')['G']==checklist('T')['G']
    assert checklist('N')['H']=={} and len(checklist('S')['H'])==5 and len(checklist('T')['H'])==9
    result=summarize_assertions(review('N','pass'),declared('N'))
    assert result['H_applicable'] is False
    assert 'common_complete' not in result and 'passed' not in result
    assert 'physical checks' in result['scope']


@pytest.mark.parametrize('fault',['binding','group_keys','invented_locator','pass_without_locator',
    'duplicate_locator','executed','extra_field','missing_audit','wrong_H'])
def test_invalid_bound_audit_is_rejected_unchanged(fault):
    value=review('N','pass')
    point=value['audit']['D']['d1']
    if fault=='binding': value['audit']['binding']['delivery_sha256']='b'*64
    if fault=='group_keys': value['audit']['G']['made_up']=copy.deepcopy(point)
    if fault=='invented_locator': point['evidence']=['receipt:invented']
    if fault=='pass_without_locator': point['evidence']=[]
    if fault=='duplicate_locator': point['evidence']=['delivery:README.md']*2
    if fault=='executed': value['tests_executed']=True
    if fault=='extra_field': value['common_complete']=True
    if fault=='missing_audit': del value['audit']
    if fault=='wrong_H': value['audit']['H']['h1']=copy.deepcopy(point)
    before=copy.deepcopy(value)
    with pytest.raises(ValueError): summarize_assertions(value,declared('N'))
    assert value==before


@pytest.mark.parametrize('fault',['bool','unknown_method','missing_binding','non_digest','duplicate_locator','bad_locator','extra'])
def test_declaration_is_explicit_exact_and_bound(fault):
    d=declared()
    if fault=='bool': d['schema']=True
    if fault=='unknown_method': d['method']='A'
    if fault=='missing_binding': d['binding'].pop('history_sha256')
    if fault=='non_digest': d['binding']['history_sha256']='path-to-something'
    if fault=='duplicate_locator': d['locators']*=2
    if fault=='bad_locator': d['locators']=[{}]
    if fault=='extra': d['forced_verdict']='accept'
    with pytest.raises(ValueError): declaration(d)


def test_common_audit_requires_explicit_nonapproval_review_request():
    d=declared()
    r={'schema':1,'role':'review','role_instructions':'Synthetic common audit only',
       'documents':{'action.txt':'review','review-response-format.json':json.dumps(d)}}
    _,prompt=render_prompt(json.dumps(r).encode())
    assert '"audit"' in prompt and 'delivery:README.md' in prompt
    validate_result(review(),'review')
    with pytest.raises(ValueError): validate_response_schema(review(),response_schema('review'))
    for role,action in [('author','author'),('review','approval')]:
        r['role']=role;r['documents']['action.txt']=action
        with pytest.raises(NativeRoleError): render_prompt(json.dumps(r).encode())


def test_no_locators_never_permits_a_pass_but_can_report_inconclusive():
    d=declared();d['locators']=[]
    validate_response_schema(review(),response_schema('review',common_audit=d))
    with pytest.raises(ValueError): validate_response_schema(review(status='pass'),response_schema('review',common_audit=d))


@pytest.mark.parametrize('schema',[1.0,True,False,'1',None,2])
def test_direct_assertion_entry_requires_exact_schema_integer(schema):
    value=review();value['schema']=schema;before=copy.deepcopy(value)
    with pytest.raises(ValueError):summarize_assertions(value,declared())
    assert value==before
