"""Resolve supplied audit locators; presence is not semantic truth/provenance.

This check is one input to the future physically verified native milestone gate.
It neither executes tests nor authenticates a model or accepts nine phases.
"""
from __future__ import annotations

import re
from specorganon.ledger import strict_json_loads
from experiments.software_comparison_v3.rubric import validate_response


class EvidenceError(ValueError):
    pass


def resolve(locator, documents):
    if type(locator) is not str or locator.count('#') != 1:
        raise EvidenceError('evidence must be document#JSONpointer')
    name, pointer = locator.split('#')
    if name not in documents or type(documents[name]) is not str:
        raise EvidenceError('evidence document absent from actual supplied snapshot')
    if not pointer:
        if not documents[name].strip(): raise EvidenceError('empty evidence document')
        return documents[name]
    if not pointer.startswith('/') or re.search(r'~(?![01])',pointer):
        raise EvidenceError('invalid JSONpointer')
    try: value = strict_json_loads(documents[name])
    except ValueError as exc: raise EvidenceError('JSONpointer requires a JSON document') from exc
    for raw in pointer[1:].split('/'):
        key = raw.replace('~1','/').replace('~0','~')
        if type(value) is dict and key in value:
            value=value[key]
        elif type(value) is list and re.fullmatch('0|[1-9][0-9]*',key) and len(key)<10 and int(key)<len(value):
            value=value[int(key)]
        else: raise EvidenceError('evidence pointer does not resolve in supplied snapshot')
    if value is None or type(value) is str and not value.strip() or type(value) in (dict,list) and not value:
        raise EvidenceError('empty evidence cannot support pass')
    return value


def verify_locators(audit, method, binding, documents):
    checked=validate_response(audit,method,binding)
    if type(documents) is not dict or any(type(k) is not str or type(v) is not str for k,v in documents.items()):
        raise EvidenceError('exact actual request documents required')
    resolved={}
    for group in ('D','G','H'):
        for identity,entry in checked[group].items():
            if entry['status']=='pass':
                resolved[group+'/'+identity]=[resolve(locator,documents) for locator in entry['evidence']]
    return {'schema':1,'all_pass_locators_resolved':True,'resolved_point_count':len(resolved),
            'scope':'presence in immutable supplied documents only; semantic/native/receipt verification still required',
            'milestone_accepted':False}
