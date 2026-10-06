"""Bound common audit syntax, not physical package or comparative proof.

Names/locators bind supplied evidence; their existence does not make semantic
judgments true. The separate verifier must check custody, chronology, independent
roles, current measured receipts and external F. H never enters the common D/G
checklist. No verdict or point status is predetermined here.
"""
from __future__ import annotations

import copy
import re

from .role_jobs import canonical
from .workflow import PHASES


D = {
    'd1': 'Environment, dependencies and executable invocation are precise.',
    'd2': 'Input/output interface, types and quantitative contract bounds are documented.',
    'd3': 'First complete example includes reproducible command, input and correct output.',
    'd4': 'Second distinct complete example includes command, input and correct output.',
    'd5': 'Contract errors, stderr/exit and atomicity are documented accurately.',
    'd6': 'Actual execution limits and scope of own tests are stated.',
    'd7': 'Semantics and requirements are explained accurately.',
    'd8': 'Tests are pertinent, reproducibly invoked and have calibrated limits.',
}
G = {
    'g1': 'Observations, documentary premises and assumptions are distinguished.',
    'g2': 'Criteria existed before own test execution, proven by captured chronology.',
    'g3': 'Requirements/criteria connect to decisions, code and pertinent tests in useful prose or artifacts.',
    'g4': 'Real own execution receipts bind argv, streams/exit and current delivery bytes.',
    'g5': 'A separate native invocation and role reviewed this exact snapshot with reasons and defects.',
    'g6': 'Conclusion limits claims to supplied evidence and reports unknown costs honestly.',
}
S = {
    'h1': 'Specification preceded code and measurements.',
    'h2': 'Design compared alternatives and recorded the choice before code.',
    'h3': 'Tasks linked requirements to work before code.',
    'h4': 'Build followed the prior plan or preserved documented changes.',
    'h5': 'Verification used real receipts and preserved unresolved failures.',
}
T = {f'h{i+1}': f'Phase {phase.id} has substantive current artifacts and accepted engine review.'
     for i,phase in enumerate(PHASES)}
BINDING_KEYS = frozenset({'contract_sha256','delivery_sha256','documents_sha256',
                          'history_sha256','policy_sha256'})


def checklist(method):
    if type(method) is not str or method not in {'N','S','T'}:
        raise ValueError('unknown common audit method')
    return copy.deepcopy({'D':D,'G':G,'H': {} if method == 'N' else S if method == 'S' else T})


def declaration(value):
    if (type(value) is not dict or set(value) != {'schema','format','method','binding','locators'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['format'] != 'common-audit-v1'
            or type(value['binding']) is not dict or set(value['binding']) != BINDING_KEYS
            or any(type(h) is not str or re.fullmatch(r'[0-9a-f]{64}',h) is None for h in value['binding'].values())
            or type(value['locators']) is not list or len(value['locators']) > 512
            or any(type(loc) is not str or not loc.strip() or len(loc)>250 for loc in value['locators'])
            or len(set(value['locators'])) != len(value['locators'])):
        raise ValueError('invalid bound common audit declaration')
    checklist(value['method']); canonical(value)
    return copy.deepcopy(value)


def audit_schema(value):
    declared = declaration(value)
    text = {'type':'string','pattern':r'\S'}
    evidence = {'type':'array','uniqueItems':True,
                'items':{'type':'string','enum':declared['locators']} if declared['locators'] else False}
    point = {'type':'object','properties':{
        'status':{'type':'string','enum':['pass','fail','inconclusive']},
        'reason':text,'evidence':evidence},
        'required':['status','reason','evidence'],'additionalProperties':False,
        'allOf':[{'if':{'properties':{'status':{'const':'pass'}}},
                  'then':{'properties':{'evidence':{'minItems':1}}}}]}
    groups = checklist(declared['method'])
    fields = {'binding':{'type':'object','properties':{
        name:{'type':'string','enum':[expected]} for name,expected in declared['binding'].items()},
        'required':sorted(BINDING_KEYS),'additionalProperties':False}}
    ref_point = {'$ref': '#/definitions/common_judgment'}
    for group,points in groups.items():
        fields[group] = {'type':'object','properties':{name:copy.deepcopy(ref_point) for name in points},
                         'required':sorted(points),'additionalProperties':False}
    return {'type':'object','definitions':{'common_judgment':point},'properties':fields,'required':list(fields),'additionalProperties':False}



def summarize_assertions(value, declared):
    """Strict parsed assertions only; deliberately no common_complete/pass proof."""
    from .native_response_contract import response_schema,validate_response_schema
    # JSON Schema treats integral floats as integers. Match the native bridge's
    # exact parsed type instead of converting 1.0 or relying on Draft7 enum.
    if type(value) is not dict or type(value.get('schema')) is not int or value['schema'] != 1:
        raise ValueError('common audit requires exact integer schema1')
    declared = declaration(declared)
    validate_response_schema(value,response_schema('review',common_audit=declared))
    groups = value['audit']
    return {'scope':'Bound reviewer assertions only; physical checks and independent F still required',
            'verdict':value['verdict'],'H_applicable':declared['method']!='N',
            'common_H_required':False,
            'counts':{group:{status:sum(p['status']==status for p in groups[group].values())
                              for status in ('pass','fail','inconclusive')} for group in ('D','G','H')}}
