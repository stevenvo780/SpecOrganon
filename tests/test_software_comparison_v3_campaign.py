"""Synthetic integration guards; no native actors, real T9 or campaign admitted."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.software_comparison_v3.campaign import Campaign,CampaignError,VerifiedTransport,AccountStop
from experiments.software_comparison_v3.provenance import ProvenanceError,NativeEvidence
from specorganon.docker_roles import DockerRoleError
from specorganon.role_jobs import _json,_write,UncertainJob


class SyntheticPhysical:
    def __init__(self,root):self.root=root;self.inspect_calls=0;self.native_calls=0;self.state='created'
    def _inspect(self,plan):self.inspect_calls+=1;return None if self.state=='missing' else {'State':{'Status':self.state}}
    def call(self,*a):self.native_calls+=1;raise DockerRoleError('synthetic failed bridge, not real native call')


class SyntheticJournal:
    def __init__(self):self.checks=0;self.outcomes=[]
    def recheck_prepared_dispatch(self,*a):self.checks+=1
    def outcome(self,*a):self.outcomes.append(a)


def wrapper(root):
    value=VerifiedTransport.__new__(VerifiedTransport);value.root=root;value.transport=SyntheticPhysical(root)
    value.journal=SyntheticJournal();value.identity='fixture-only';return value


@pytest.mark.parametrize('state',['missing','running','exited'])
def test_prepared_handle_not_created_is_never_restarted(tmp_path,state):
    value=wrapper(tmp_path);value.transport.state=state
    (tmp_path/'jobs'/'existing').mkdir(parents=True);_write(tmp_path/'jobs/existing/launch.json',{'fixture':'no physical handle'})
    with pytest.raises(UncertainJob):value.pre_dispatch('existing','roles')
    assert value.journal.checks==value.transport.native_calls==0


def test_unstarted_dispatch_checks_existing_budget_but_started_handle_does_not_allocate(tmp_path):
    value=wrapper(tmp_path);value.pre_dispatch('prepared','roles');assert value.journal.checks==1
    journal=tmp_path/'host-journal/prepared';journal.mkdir(parents=True);_write(journal/'started.json',{'fixture':True})
    value.pre_dispatch('prepared','roles')
    assert value.journal.checks==1 and value.transport.native_calls==0


def test_failure_without_physical_closed_witness_remains_pending(tmp_path):
    value=wrapper(tmp_path)
    def unresolved(*a):raise ProvenanceError('synthetic missing receipt')
    value.evidence=SimpleNamespace(failed_role=unresolved)
    with pytest.raises(UncertainJob):value.call('fixture-role','author',{'fixture':'not actual prompt'})
    assert value.transport.native_calls==1 and value.journal.outcomes==[]


@pytest.mark.parametrize('status',['generation_failed','infra_inconclusive'])
def test_only_verified_failure_records_consumed_outcome_and_unknown_stops(tmp_path,status):
    value=wrapper(tmp_path);value.evidence=SimpleNamespace(failed_role=lambda *a:{'status':status,'reason':'synthetic witness fixture'})
    with pytest.raises(AccountStop if status=='infra_inconclusive' else DockerRoleError):value.call('fixture-role','author',{})
    assert len(value.journal.outcomes)==1 and value.transport.native_calls==1
    assert value.journal.outcomes[0][-1]['actual_failed_execution']['status']==status


@pytest.mark.parametrize('diagnostic,expected',[
    ('native role inconclusive: NativeRoleError: invalid author result contract','generation_failed'),
    ('native role inconclusive: NativeRoleError: native process failed, timed out, truncated or could not receive full input','infra_inconclusive'),
    ('401 Unauthorized quota retry somewhere','infra_inconclusive')])
def test_failure_classifier_does_not_infer_account_recovery_from_diagnostic(tmp_path,monkeypatch,diagnostic,expected):
    # Mocked inspection/receipt: classification control only, not physical proof.
    value=NativeEvidence.__new__(NativeEvidence)
    plan={'container_id':'synthetic','request_sha256':'a'*64}
    receipt={'exit_code':1,'timed_out':False,'truncated_streams':[]}
    monkeypatch.setattr(value,'_execution',lambda *a,**k:(tmp_path,plan,{'fixture':True},receipt,{'stderr':diagnostic.encode()}))
    monkeypatch.setattr(value,'_source_snapshot',lambda *a:None)
    proof=value.failed_role('fixture-role','author',{'fixture':True})
    assert proof['status']==expected and proof['positive_acceptance'] is False and proof['native_restarted'] is False


def test_campaign_cannot_construct_with_unregistered_dict(tmp_path):
    with pytest.raises(CampaignError,match='full Registration'):Campaign({'status':'registered'},tmp_path/'quota')
