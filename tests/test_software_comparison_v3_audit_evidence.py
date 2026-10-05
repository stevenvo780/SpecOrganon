"""Locator presence controls, not substantive reviewer or method acceptance."""
import pytest
from experiments.software_comparison_v3.audit_evidence import resolve,verify_locators,EvidenceError
from experiments.software_comparison_v3.rubric import rubric


def test_resolves_exact_JSONpointer_escapes_arrays_and_false_zero_evidence():
    docs={'x.json':'{"a/b":{"~":[0,false,"actual excerpt"]}}','contract.md':'Actual supplied contract'}
    assert resolve('x.json#/a~1b/~0/0',docs)==0
    assert resolve('x.json#/a~1b/~0/1',docs) is False
    assert resolve('x.json#/a~1b/~0/2',docs)=='actual excerpt'
    assert resolve('contract.md#',docs)=='Actual supplied contract'


@pytest.mark.parametrize('locator',['absent.md#','x.json#/missing','x.json#/list/-','x.json#/list/01','x.json#/list/999','x.json#/a~2b','x.json#notpointer','contract.md#/line','x.json##/a','no-fragment'])
def test_rejects_missing_ambiguous_or_invented_locations(locator):
    with pytest.raises(EvidenceError):resolve(locator,{'x.json':'{"list":["entry"]}','contract.md':'Plain contract'})


@pytest.mark.parametrize('value',['null','" "','[]','{}'])
def test_empty_resolved_location_cannot_support_pass(value):
    with pytest.raises(EvidenceError):resolve('x.json#/item',{'x.json':'{"item":'+value+'}'})


def test_all_pass_points_need_resolving_evidence_but_presence_never_accepts_milestone():
    binding={k:'a'*64 for k in ('contract_sha256','delivery_sha256','history_sha256')}
    audit={'schema':1,'binding':binding,'reason':'Synthetic controls only','tests_executed':False}
    for group in 'DGH':audit[group]={i:{'status':'pass','reason':'Presence fixture, not quality.','evidence':['contract.md#']} for i in rubric('N')[group]}
    result=verify_locators(audit,'N',binding,{'contract.md':'Synthetic context'})
    assert result['resolved_point_count']==14 and result['milestone_accepted'] is False
    audit['G']['g4']['evidence']=['invented-receipt.json#/exit_code']
    with pytest.raises(EvidenceError):verify_locators(audit,'N',binding,{'contract.md':'Synthetic context'})
