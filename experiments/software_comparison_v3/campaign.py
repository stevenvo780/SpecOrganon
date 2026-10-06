"""Fixed-order v3 generation, verified transport, terminal snapshots and T9 gate.

Only full immutable Registration permits constructing native cells. No authors,
accounts, recipes, cohorts or substituted outputs are selected dynamically.
CLI steps one action, leaving fresh quota updates and same-handle recovery to the
coordinator. No reserved Subjects is constructed by generation or status reads.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path

from specorganon import engine
from specorganon.docker_roles import DockerRoles,DockerRoleError
from specorganon.role_jobs import JobError,UncertainJob,canonical,digest,_json,_read,_write,_safe
from specorganon.software_controller import encoded_contribution,safe_file
from experiments.software_comparison_v3.registration import Registration,current_quota,RegistrationError
from experiments.software_comparison_v3.budget import RunJournal,RoleBudget,BudgetError,ClockUnknown
from experiments.software_comparison_v3.cells import BasicCell,ToolkitCell
from experiments.software_comparison_v3.provenance import NativeEvidence,ProvenanceError,MilestoneRejected,toolkit_milestone


class CampaignError(ValueError):pass
class AccountStop(ValueError):pass


class VerifiedTransport:
    """Physical success before budget outcomes; actual failed witness before seal."""
    def __init__(self,transport,journal,identity):
        self.transport=transport;self.root=transport.root;self.journal=journal;self.identity=identity
        self.evidence=NativeEvidence(transport)

    def pre_dispatch(self,job_id,kind):
        journal=self.root/'host-journal'/job_id
        if not (journal/'started.json').exists() and not (journal/'receipt.json').exists():
            plan=self.root/'jobs'/job_id/'launch.json'
            if plan.exists():
                value=self.transport._inspect(_json(plan))
                if value is None or value['State']['Status']!='created':
                    raise UncertainJob('prepared handle missing/previously started; never create replacement')
            self.journal.recheck_prepared_dispatch(self.identity,job_id,kind)

    def call(self,job_id,role,request):
        self.pre_dispatch(job_id,'roles')
        try:
            packet=self.transport.call(job_id,role,request)
        except DockerRoleError:
            # Absence of a closed receipt, live/missing handle or failed physical
            # binding cannot be promoted to a terminal native result here.
            try:failure=self.evidence.failed_role(job_id,role,request)
            except (JobError,ProvenanceError) as exc:
                raise UncertainJob('native dispatch failure lacks verified closed terminal witness') from exc
            self.journal.outcome(self.identity,job_id,'roles',{'actual_failed_execution':failure})
            if failure['status']=='infra_inconclusive':raise AccountStop(failure['reason'])
            raise
        self.evidence.role(job_id,role,request=request,packet=packet)
        return packet

    def measure(self,job_id,argv,files):
        self.pre_dispatch(job_id,'tests')
        measured=self.transport.measure(job_id,argv,files)
        self.evidence.test(job_id,files,require_passed=False)
        return measured

    def verify_test(self,*args,**kwargs):return self.transport.verify_test(*args,**kwargs)


class Campaign:
    def __init__(self,registration,quota_snapshot):
        if type(registration) is not Registration:raise CampaignError('full Registration object required')
        self.registration=registration;registration.validate();self.value=registration.value
        self.source=registration.source;self.root=_safe(self.value['run_root']);self.quota=_safe(quota_snapshot)
        self.journal=RunJournal(self.root/'budget',registration_sha256=registration.sha,
            cells=[{'id':c['id'],'method':c['method']} for c in self.value['cells']],
            validate_registration=registration.validate,validate_quota=lambda:current_quota(self.quota))
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.lock():
            path=self.root/'campaign.json';policy={'schema':1,'registration_sha256':registration.sha,
                'source_root':str(self.source),'cells':self.value['cells'],'primary_T':'cell-01'}
            if path.exists() and _json(path)!=policy:raise CampaignError('campaign source/order changed')
            if not path.exists():_write(path,policy)
            path=self.root/'progress.json'
            if not path.exists():_write(path,{'schema':1,'steps':{},'actual_native_stop':None,'evaluation':None})

    @contextmanager
    def lock(self):
        fd=os.open(self.root/'.campaign.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:raise CampaignError('another campaign writer is active') from exc
            yield
        finally:os.close(fd)

    def cell(self,row):
        self.registration.validate()
        root=self.root/'cells'/row['id'];other='gemini' if row['family']=='codex' else 'codex'
        a=self.value['routes'][row['family']];r=self.value['routes'][other]
        physical=DockerRoles(root/'transport',source_root=self.source,
            native_image=self.value['images']['native'],test_image=self.value['images']['test'],
            public_catalog=self.source/self.value['public_catalog'],
            author_provider=a['provider'],author_model=a['model'],reviewer_provider=r['provider'],reviewer_model=r['model'],
            codex_reasoning_effort='medium',**self.value['profiles'])
        verified=VerifiedTransport(physical,self.journal,row['id'])
        budget=RoleBudget(self.journal,row['id'],verified)
        common={'task':row['task'],'contract':_read(self.source/self.value['contracts'][row['task']]).decode(),
            'mandate':_read(self.source/self.value['mandate']).decode(),'protocol_sha256':self.registration.sha,
            'rubric':_read(self.source/self.value['rubric']).decode()}
        if row['method']=='T':runner=ToolkitCell(root/'generation',budget,**common)
        else:runner=BasicCell(root/'generation',budget,method=row['method'],
            sdd_guide=_read(self.source/self.value['sdd_guide']).decode(),**common)
        return runner,verified.evidence

    def snapshot(self,row,runner,status):
        """Private outcome/method records separate from opaque files-only input."""
        if row['method']=='T':
            files=runner.controller._files();process={'state':engine.get_state(runner.case),
                'history':_json(runner.controller.root/'progress.json')['history']}
        else:
            state=_json(runner.root/'progress.json');files=state['files']
            process={k:state[k] for k in ('process','candidate_items','history','measurements')}
        if encoded_contribution(files)>20000:raise CampaignError('terminal delivery exceeded registered file ceiling')
        for name in files:safe_file(name)
        return {'schema':1,'cell_id':row['id'],'opaque_id':row['opaque_id'],'method':row['method'],
                'task':row['task'],'status':status,'files':files,'process':process,
                'delivery_sha256':digest(canonical(files)),'registration_sha256':self.registration.sha}

    def seal(self,row,runner,status):
        snapshot=self.snapshot(row,runner,status);folder=self.root/'exports'/row['opaque_id']
        folder.mkdir(parents=True,mode=0o700,exist_ok=True)
        export={'schema':1,'opaque_id':row['opaque_id'],'task':row['task'],'files':snapshot['files'],
                'delivery_sha256':snapshot['delivery_sha256']}
        # Root/private mapping is never passed to Subjects or mounted to roles.
        for path,value in [(folder/'delivery.json',export),(self.root/'cells'/row['id']/'terminal-snapshot.json',snapshot)]:
            if path.exists() and _json(path)!=value:raise CampaignError('sealed snapshot/export changed')
            if not path.exists():_write(path,value)
        seal=self.journal.close_cell(row['id'],status=status,delivery_sha256=snapshot['delivery_sha256'])
        return {'status':status,'snapshot_sha256':digest(canonical(snapshot)),
                'export_sha256':digest(canonical(export)),'seal':seal}

    def step(self):
        with self.lock():
            self.registration.validate();state=_json(self.root/'progress.json')
            if state['actual_native_stop'] is not None:raise AccountStop('fixed campaign stopped after actual unknown native failure; no automatic resume/fallback')
            progress=_json(self.journal.root/'progress.json')
            row=next((c for c in self.value['cells'] if progress['cells'][c['id']]['terminal'] is None),None)
            if row is None:return {'action':'all_generation_terminal','cells':42,'reserved_evaluation_allowed':False}
            if progress['cells'][row['id']]['clock'] is None:current_quota(self.quota)
            runner,evidence=self.cell(row)
            try:result=runner.step()
            except AccountStop as exc:
                result={'action':'infra_inconclusive','reason':str(exc),'automatic_retry':False}
                state['actual_native_stop']={'cell_id':row['id'],'reason':str(exc)}
            except (UncertainJob,RegistrationError,ClockUnknown,ProvenanceError):
                # No invented terminal outcome or clock reset; exact pending
                # role/handle remains in cell and transport journals.
                raise
            state['steps'].setdefault(row['id'],[]).append(result)
            terminal=('infra_inconclusive' if result['action']=='infra_inconclusive' else
                      'generation_failed' if result['action']=='failed' else
                      'complete' if result['action']=='complete' or result.get('complete') else None)
            if terminal is not None:
                # Outcome/receipt checks in the journal refuse unresolved jobs.
                result={**result,'terminal':self.seal(row,runner,terminal)}
            _write(self.root/'progress.json',state)
            return {'cell_id':row['id'],'method':row['method'],**result}

    def verify_milestone(self,identity,seal):
        row=next(c for c in self.value['cells'] if c['id']==identity)
        snapshot=_json(self.root/'cells'/identity/'terminal-snapshot.json')
        if snapshot['delivery_sha256']!=seal['delivery_sha256']:raise CampaignError('terminal milestone delivery changed')
        if seal['status']=='generation_failed':
            proof={'status':'failed','reason':'fixed T generation failed before native9 completion',
                   'snapshot_sha256':digest(canonical(snapshot))}
        elif seal['status']=='infra_inconclusive':
            proof={'status':'inconclusive','reason':'native generation infrastructure unknown',
                   'snapshot_sha256':digest(canonical(snapshot))}
        else:
            runner,evidence=self.cell(row)
            try:proof=toolkit_milestone(runner,evidence)
            except MilestoneRejected as exc:
                proof={'status':'failed','reason':str(exc),'snapshot_sha256':digest(canonical(snapshot))}
            except (ProvenanceError,JobError,ValueError) as exc:
                proof={'status':'inconclusive','reason':'current native milestone not conclusively proven: '+type(exc).__name__}
        path=self.root/'cells'/identity/'milestone-proof.json'
        if path.exists() and _json(path)!=proof:
            previous=_json(path)
            if previous['status']!='inconclusive':raise CampaignError('conclusive milestone proof changed')
            archive=path.parent/'milestone-observations';archive.mkdir(mode=0o700,exist_ok=True)
            original=archive/(digest(canonical(previous))+'.json')
            if not original.exists():_write(original,previous)
        if not path.exists() or _json(path)!=proof:_write(path,proof)
        return {'status':proof['status'],'evidence_sha256':digest(canonical(proof))}

    def gate(self):
        with self.lock():return self.journal.evaluation_gate(self.verify_milestone)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['validate','status','step','gate','evaluate-step','report'])
    p.add_argument('--registration',required=True,type=Path);p.add_argument('--source',required=True,type=Path)
    p.add_argument('--quota',type=Path)
    a=p.parse_args(argv);registration=Registration(a.registration,a.source)
    if a.command=='validate':result=registration.validate()
    elif a.command=='status':
        root=_safe(registration.value['run_root']);path=root/'budget/progress.json'
        result={'registration_sha256':registration.sha,'generation':_json(path) if path.exists() else 'not_admitted',
                'reserved_subjects_invoked_by_status':False}
    else:
        if a.quota is None:p.error('--quota is required for generation/gate')
        campaign=Campaign(registration,a.quota)
        if a.command=='step':result=campaign.step()
        elif a.command=='gate':result=campaign.gate()
        else:
            from experiments.software_comparison_v3.evaluation import Evaluation
            evaluator=Evaluation(campaign);result=evaluator.step() if a.command=='evaluate-step' else evaluator.report()
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
