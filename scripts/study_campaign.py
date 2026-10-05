"""Sequential, preregistered campaign admission; original accounts only.

Quota snapshots come from the coordinator's current quota tools. They contain
observations, not credentials or a promise of capacity. No provider fallback,
new cell, raised budget or retry of a terminal cell is selected here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from specorganon.docker_roles import DockerRoles, DockerRoleError
from specorganon.role_jobs import JobError, UncertainJob, canonical, digest, _read, _json, _write, _safe
from specorganon.software_controller import ControllerError, safe_file, encoded_contribution
from scripts.software_study_harness import BasicCell, ToolkitCell, StudyHarnessError, registration
from scripts.study_cell_budget import CellBudget, StudyBudgetError, StudyClockPause
from scripts.controller_native_role import NativeRoleError
from scripts.controller_native_role import role_model_catalog


class CampaignPause(ValueError):
    """No new call admitted; resume same pending input with fresh quota evidence."""


class AccountStop(ValueError):
    """Actual native failure consumed the cell; campaign stops without fallback."""


def utc(text):
    if type(text) is not str: raise StudyHarnessError('timestamp must be text')
    try: value=dt.datetime.fromisoformat(text.replace('Z','+00:00'))
    except ValueError as exc: raise StudyHarnessError('invalid UTC timestamp') from exc
    if value.utcoffset()!=dt.timedelta(0): raise StudyHarnessError('UTC timestamp required')
    return value.timestamp()


def current_quota(path, *, now=None):
    raw=_read(path,128000); value=_json(path); now=time.time() if now is None else now
    if (type(value) is not dict or value.get('schema')!=1
            or value.get('accounts')!= {'codex':'original_lab_profile','gemini':'original_primary_profile'}):
        raise CampaignPause('current original-account quota snapshot required')
    age=now-utc(value.get('captured_at'))
    if not 0<=age<=600: raise CampaignPause('quota snapshot older than600s or future-dated')
    providers=value.get('providers')
    if type(providers) is not dict or set(providers)!={'codex','gemini'}:
        raise CampaignPause('both original provider observations required')
    for provider,row in providers.items():
        if (type(row) is not dict or row.get('status') not in {'observed','unknown'}
                or type(row.get('remaining_percent')) is not list):
            raise CampaignPause('invalid quota observation')
        numbers=row['remaining_percent']
        if row['status']=='unknown':
            if set(row)!={'status','remaining_percent','reason'} or numbers or not row.get('reason'):
                raise CampaignPause('unknown quota must remain explicit')
        else:
            if (set(row)!={'status','remaining_percent','source','observed_at'}
                    or not numbers or any(type(n) not in {int,float} or not 0<=n<=100 for n in numbers)
                    or not row.get('source') or not 0<=now-utc(row.get('observed_at'))<=600):
                raise CampaignPause('stale/malformed provider observation')
            if min(numbers)==0: raise CampaignPause(provider+' quota depleted; no native submission')
    return {'quota_snapshot_sha256':digest(raw),'captured_at':value['captured_at'],
            'capacity_guaranteed':False,'observations':providers}


def validate_configuration(value, source):
    expected_routes={'codex':{'provider':'codex','model':'gpt-6.1-sol'},
                     'gemini':{'provider':'gemini','model':'gemini-3.1-pro-high'}}
    if value.get('routes')!=expected_routes or value.get('codex_reasoning_effort')!='low':
        raise StudyHarnessError('fixed inspected two-family routes/effort required')
    profiles={'codex_volume':'specorganon-lab_codex-home','gemini_profile':'/home/stev/.gemini',
              'gemini_executable':'/home/stev/.local/bin/agy'}
    if value.get('profiles')!=profiles: raise StudyHarnessError('original profiles required; no account fallback')
    images=value.get('images')
    if (type(images) is not dict or set(images)!={'native','test'}
            or any(type(s) is not str or re.fullmatch('sha256:[0-9a-f]{64}',s) is None for s in images.values())):
        raise StudyHarnessError('immutable inspected native/test images required')
    limits=value.get('limits')
    if (type(limits) is not dict or set(limits)!={'max_calls','max_total_input_bytes','max_elapsed_seconds'}
            or limits['max_calls']!=40 or limits['max_elapsed_seconds']!=6000
            or type(limits['max_total_input_bytes']) is not int
            or not 1<=limits['max_total_input_bytes']<=5_120_000):
        raise StudyHarnessError('explicit common prospective cell budget required')
    if value.get('stopping_rule')!='terminal_cell_no_retry_pause_campaign_on_account_or_unknown_native_failure':
        raise StudyHarnessError('fixed stopping rule required')
    root=_safe(value.get('run_root',''))
    if not Path(value.get('run_root','')).is_absolute() or root==source or source in root.parents:
        raise StudyHarnessError('fixed private campaign root must be outside source checkout')
    catalog=value.get('public_catalog')
    if type(catalog) is not str or catalog not in value['source_sha256']:
        raise StudyHarnessError('public model catalog must be source-bound')
    validate_model_catalog(value,source)
    registered=utc(value.get('registered_at'))
    if registered>time.time(): raise StudyHarnessError('future registration not admissible')
    review=_json(source/value['independent_review_receipt'])
    if (type(review) is not dict or review.get('schema')!=1 or review.get('verdict')!='accept'
            or review.get('scope')!='full_protocol_harness_rubric_and_evaluator'
            or type(review.get('job_id')) is not str or not review['job_id']
            or type(review.get('source_sha256')) is not dict):
        raise StudyHarnessError('full independent acceptance required, not scoped draft review')
    bound={p:sha for p,sha in value['source_sha256'].items() if p!=value['independent_review_receipt']}
    if review['source_sha256']!=bound or utc(review.get('completed_at'))>registered:
        raise StudyHarnessError('reviewed source snapshot differs from registration')
    return root


def validate_model_catalog(value,source):
    """Provider runtime metadata is distinct from the MCP route registry.

    Check the same public model/effort contract as the bridge before creating
    a campaign or admitting any native job. Never substitute metadata at runtime.
    """
    try:
        catalog=_json(source/value['public_catalog'])
        projected=role_model_catalog(catalog,value['routes']['codex']['model'])
        supported=projected['models'][0].get('supported_reasoning_levels',[])
        if type(supported) is not list or not any(type(row) is dict and
                row.get('effort')==value['codex_reasoning_effort'] for row in supported):
            raise StudyHarnessError('runtime catalog does not support registered Codex effort')
    except NativeRoleError as exc:
        raise StudyHarnessError('Codex runtime catalog invalid before admission: '+str(exc)) from exc
    return digest(_read(source/value['public_catalog'],8_388_608))


def export_delivery(root, cell, registration_sha256, *, files, process, outcome):
    """Seal bytes for a separate opaque evaluator, retaining partial deliveries."""
    if encoded_contribution(files)>20000: raise StudyHarnessError('export exceeds common file budget')
    opaque='delivery-'+digest(canonical({'registration':registration_sha256,'cell':cell['id']}))[:24]
    target=_safe(root/'deliveries'/opaque)
    # The functional evaluator reads only these files, never process/outcome/method.
    payload={'schema':1,'opaque_id':opaque,'task':cell['task'],'files':files,
             'files_sha256':digest(canonical(files))}
    packet=target/'delivery.json'
    if packet.exists():
        if _json(packet)!=payload: raise StudyHarnessError('sealed export changed')
    else:
        target.mkdir(parents=True,mode=0o700,exist_ok=True)
        for name,text in files.items():
            name=safe_file(name); path=_safe(target/'files'/name)
            path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
            # Unsealed copies can be reconstructed from the already fixed
            # source map, without regenerating an author or changing bytes.
            fd,temp=tempfile.mkstemp(prefix='.export-',dir=path.parent)
            try:
                with os.fdopen(fd,'wb') as output:
                    output.write(text.encode());output.flush();os.fsync(output.fileno())
                    os.fchmod(output.fileno(),0o444)
                os.replace(temp,path)
            finally:
                try: os.unlink(temp)
                except FileNotFoundError: pass
        _write(packet,payload)
    for name,text in files.items():
        if _read(target/'files'/name).decode()!=text: raise StudyHarnessError('exported file changed')
    private=root/'cells'/cell['id']/'export-record.json'
    record={'opaque_id':opaque,'cell':cell,'outcome':outcome,'process':process,
            'delivery_sha256':payload['files_sha256'],'functional_feedback_used':False}
    if private.exists() and _json(private)!=record: raise StudyHarnessError('closed outcome changed')
    if not private.exists(): _write(private,record)
    return {'opaque_id':opaque,'delivery_sha256':payload['files_sha256']}


def native_failure_kind(root):
    """Classify only actual failed bridge diagnostics; never inspect prompt text.

Unknown native failures pause the campaign rather than silently changing accounts
or admitting more jobs. Controlled role-format failures close only their cell.
"""
    candidates=[]
    for path in (root/'jobs').glob('*/launch.json'):
        plan=_json(path)
        if plan.get('role')=='test': continue
        receipt=root/'host-journal'/plan['job_id']/'receipt.json'
        if receipt.exists():
            record=_json(receipt)
            if record['exit_code'] or record['timed_out'] or record['truncated_streams']:
                candidates.append((record['finished_epoch'],path.parent))
    if not candidates: return 'unclassified_native_failure'
    _,folder=max(candidates,key=lambda item:item[0])
    job_id=_json(folder/'launch.json')['job_id']
    raw=_read(root/'host-journal'/job_id/'stderr.bin').decode(errors='replace')
    prefix='native role inconclusive: NativeRoleError: '
    controlled={'invalid role result schema','invalid review result contract',
                'invalid author result contract','invalid exact finite JSON',
                'empty role response','role response must be one JSON object',
                'multiple native final messages','native Codex response is incomplete',
                'incomplete Gemini native stream'}
    if raw.strip() in {prefix+message for message in controlled}: return 'invalid_native_role_format'
    return 'unclassified_native_failure'


class ObservedTransport:
    def __init__(self,transport): self.transport=transport
    def call(self,*args,**kwargs):
        try: return self.transport.call(*args,**kwargs)
        except DockerRoleError as exc:
            if native_failure_kind(self.transport.root)=='invalid_native_role_format': raise
            raise AccountStop('actual native failure; account/quota cause unknown; no fallback') from exc
    def measure(self,*args,**kwargs): return self.transport.measure(*args,**kwargs)
    def verify_test(self,*args,**kwargs): return self.transport.verify_test(*args,**kwargs)
    def test_record(self,job_id):
        if type(job_id) is not str or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',job_id) is None:
            raise StudyHarnessError('invalid historical test ID')
        return _json(self.transport.root/'jobs'/job_id/'measured-test.json')


class Campaign:
    def __init__(self,root,value,sha,*,source,quota_snapshot,fixture_mode=False,cell_factory=None):
        self.root=_safe(root);self.root.mkdir(parents=True,mode=0o700,exist_ok=True)
        info=self.root.stat()
        if info.st_uid!=os.geteuid() or info.st_mode&0o022: raise StudyHarnessError('private owned campaign root required')
        self.value=value;self.sha=sha;self.source=source;self.quota=quota_snapshot
        self.fixture=fixture_mode;self.cell_factory=cell_factory
        if fixture_mode:
            if value.get('status')!='synthetic_fixture' or cell_factory is None:
                raise StudyHarnessError('explicit synthetic fixture factory required')
        elif cell_factory is not None or self.root!=validate_configuration(value,source):
            raise StudyHarnessError('native campaign root/configuration changed')
        policy={'schema':1,'registration_sha256':sha,'cells':value['cells'],'fixture_mode':fixture_mode}
        with self.lock():
            path=self.root/'campaign.json'
            if path.exists() and _json(path)!=policy: raise StudyHarnessError('campaign registration/order changed')
            if not path.exists(): _write(path,policy)
            if not (self.root/'progress.json').exists():
                _write(self.root/'progress.json',{'schema':1,'cells':{},'next_index':0,'paused':None})

    @contextmanager
    def lock(self):
        fd=os.open(self.root/'.campaign.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc: raise StudyHarnessError('campaign already has an active writer') from exc
            yield
        finally: os.close(fd)

    def validate(self):
        if self.fixture: return {'classification':'synthetic control, no native provider'}
        value,sha=registration(self.value['_path'],self.source)
        if sha!=self.sha: raise StudyHarnessError('registration changed after campaign admission')
        validate_configuration(value,self.source)
        return current_quota(self.quota)

    def _cell(self,cell):
        if self.fixture: return self.cell_factory(cell,self.root/'cells'/cell['id'])
        root=self.root/'cells'/cell['id'];root.mkdir(parents=True,mode=0o700,exist_ok=True)
        other='gemini' if cell['family']=='codex' else 'codex'
        a=self.value['routes'][cell['family']];r=self.value['routes'][other]
        transport=DockerRoles(root/'transport',native_image=self.value['images']['native'],
            test_image=self.value['images']['test'],source_root=self.source,
            public_catalog=self.source/self.value['public_catalog'],
            author_provider=a['provider'],author_model=a['model'],reviewer_provider=r['provider'],reviewer_model=r['model'],
            codex_reasoning_effort=self.value['codex_reasoning_effort'],**self.value['profiles'])
        budget=CellBudget(root/'budget',protocol_sha256=self.sha,transport=ObservedTransport(transport),
                          validate=self.validate,**self.value['limits'])
        public=self.source/'experiments/software_comparison_v1/public'
        common={'task':cell['task'],'contract':_read(public/(cell['task']+'.md')).decode(),
                'protocol_sha256':self.sha,'rubric':_read(self.source/self.value['rubric']).decode()}
        if cell['method']=='T':
            return ToolkitCell(root/'generation',budget,mandate=_read(self.source/self.value['mandate']).decode(),**common)
        return BasicCell(root/'generation',budget,method=cell['method'],sdd_guide=_read(public/'sdd-guide.md').decode(),**common)

    def _export(self,cell,result):
        root=self.root/'cells'/cell['id']/'generation'
        if self.fixture: return {'classification':'synthetic outcome control'}
        if cell['method']=='T':
            delivery=root/'controller/delivery'
            files={str(p.relative_to(delivery)):_read(p).decode() for p in delivery.rglob('*') if p.is_file()}
            process={'state':_json(root/'last-read-status.json')} if (root/'last-read-status.json').exists() else {}
            if (root/'case/organon.json').exists():
                from specorganon import engine
                process={'state':engine.get_state(root/'case'),'report':case_report_safe(root/'case')}
            review=(_json(root/'common-final-review.json')['result']
                    if (root/'common-final-review.json').exists() else None)
        else:
            state=_json(root/'progress.json'); files=state['files'];process=state['process']
            if state['complete'] and not state.get('terminal_failure'):
                # Recheck the closed native review/input binding before copying.
                runner=BasicCell(root,None,method=cell['method'],task=cell['task'],
                    contract=_read(self.source/'experiments/software_comparison_v1/public'/(cell['task']+'.md')).decode(),
                    sdd_guide=_read(self.source/'experiments/software_comparison_v1/public/sdd-guide.md').decode(),
                    protocol_sha256=self.sha,rubric=_read(self.source/self.value['rubric']).decode())
                runner.validate_closed(state)
            review=state.get('final_review')
        # Stable terminal outcome, independent of which final step was replayed
        # after a crash between export and campaign checkpoint persistence.
        status=result.get('action') if result.get('action') in {'failed','infra_inconclusive'} else 'complete'
        outcome={'status':status,
                 'final_review':review,'failure':result.get('failure')}
        return export_delivery(self.root,cell,self.sha,files=files,process=process,outcome=outcome)

    def step(self,cell_id):
        with self.lock():
            state=_json(self.root/'progress.json')
            if cell_id in state['cells'] and state['cells'][cell_id]['status'] in {'complete','failed','infra_inconclusive'}:
                return state['cells'][cell_id]
            if state['paused'] and state['paused'].get('actual_native_failure'):
                raise CampaignPause('campaign stopped after actual native failure; no automatic resume')
            index=state['next_index']
            if index>=len(self.value['cells']): raise StudyHarnessError('fixed campaign already terminal')
            cell=self.value['cells'][index]
            if cell['id']!=cell_id: raise StudyHarnessError('cell is not next in preregistered order')
            try:
                observed=self.validate()
                state['paused']=None
                record=state['cells'].setdefault(cell_id,{'status':'running','cell':cell,'steps':[]})
                record['last_preflight']=observed
                _write(self.root/'progress.json',state)
                runner=self._cell(cell)
                try: result=runner.step()
                except (ControllerError,StudyBudgetError,StudyHarnessError,NativeRoleError,UncertainJob) as exc:
                    result={'action':'failed','failure':{'error_type':type(exc).__name__,'reason':str(exc),
                                                       'automatic_retry':False,'grade':None}}
                record['steps'].append(result)
                if result.get('action') in {'complete','failed'} or result.get('complete'):
                    record['status']='failed' if result.get('action')=='failed' else 'complete'
                    record['export']=self._safe_export(cell,result);state['next_index']+=1
                _write(self.root/'progress.json',state)
                return record
            except (CampaignPause,StudyClockPause) as exc:
                state['paused']={'reason':str(exc),'actual_native_failure':False}
                _write(self.root/'progress.json',state)
                raise
            except AccountStop as exc:
                result={'action':'infra_inconclusive','failure':{'reason':str(exc),'automatic_retry':False,
                        'admission_consumed':True,'grade':None}}
                record=state['cells'][cell_id];record['status']='infra_inconclusive';record['steps'].append(result)
                record['export']=self._safe_export(cell,result)
                state['paused']={'reason':str(exc),'actual_native_failure':True}
                _write(self.root/'progress.json',state)
                return record

    def _safe_export(self,cell,result):
        try: return self._export(cell,result)
        except (StudyHarnessError,JobError) as exc:
            return {'status':'inconclusive','reason':str(exc),'raw_generation_retained':True,
                    'native_retry':False,'grade':None}


def case_report_safe(path):
    from specorganon.report import case_report
    return case_report(path)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration',type=Path,required=True)
    parser.add_argument('--cell',required=True)
    parser.add_argument('--quota-snapshot',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--steps',type=int,default=1)
    args=parser.parse_args(argv)
    if not 1<=args.steps<=80: parser.error('--steps must be1..80')
    value,sha=registration(args.registration,args.source_root)
    root=validate_configuration(value,args.source_root)
    value={**value,'_path':str(args.registration.absolute())}
    campaign=Campaign(root,value,sha,source=args.source_root,quota_snapshot=args.quota_snapshot)
    for _ in range(args.steps):
        result=campaign.step(args.cell);print(json.dumps(result,ensure_ascii=False),flush=True)
        if result['status'] in {'complete','failed','infra_inconclusive'}: break


if __name__=='__main__':
    try: main()
    except (ValueError,OSError) as exc:
        print(json.dumps({'status':'stopped','reason':str(exc),'new_call_retry':False}),file=sys.stderr)
        raise SystemExit(2)
