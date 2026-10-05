"""Prospective cell execution. CLI refuses drafts; no reserved feedback is used.

This is engineering infrastructure, not a preregistration. A supplied registration
must bind all relevant sources and the full fixed population before native calls.
The ablation stores unaccepted phase drafts outside the engine, never approvals.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from specorganon import engine
from specorganon.docker_roles import DockerRoles, DockerRoleError
from specorganon.report import case_report
from specorganon.runner import describe_task
from specorganon.role_jobs import canonical, digest, _read, _json, _write, _safe, UncertainJob
from specorganon.software_controller import Controller, ControllerError, encoded_contribution, safe_file
from specorganon.workflow import PHASES
from scripts.controller_native_role import render_prompt, validate_result, NativeRoleError
from scripts.study_cell_budget import CellBudget, StudyBudgetError
from scripts.study_assessment import instructions as assessment_instructions, observe as observe_assessment


class StudyHarnessError(ValueError):
    pass


REQUIRED_SOURCES = {
    'scripts/software_study_harness.py', 'scripts/study_cell_budget.py',
    'scripts/study_campaign.py', 'scripts/study_assessment.py',
    'scripts/controller_native_role.py', 'src/specorganon/software_controller.py',
    'src/specorganon/docker_roles.py', 'src/specorganon/role_jobs.py',
    'experiments/software_comparison_v1/public/routeplan.md',
    'experiments/software_comparison_v1/public/treemap.md',
    'experiments/software_comparison_v1/public/sdd-guide.md',
    'experiments/software_comparison_v1/public/existing-mandate.md',
    'experiments/software_comparison_v1/public/assessment-rubric.md',
    'experiments/software_comparison_v1/reserved/evaluator.py',
    'experiments/software_comparison_v1/reserved/docker_evaluator.py',
    'experiments/software_comparison_v1/reserved/trace_collector.py',
    'experiments/software_comparison_v1/reserved/campaign_evaluation.py',
    'experiments/software_comparison_v1/reserved/suite-draft.json',
}


def registration(path, source):
    source=_safe(source)
    raw = _read(path, 2_097_152); value = _json(path)
    if (type(value) is not dict or value.get('schema') != 2
            or value.get('status') != 'preregistered'
            or not value.get('independent_review_receipt')
            or not value.get('protocol') or not value.get('rubric')
            or not value.get('mandate') or not value.get('stopping_rule')):
        raise StudyHarnessError('reviewed full preregistration required before generation')
    hashes = value.get('source_sha256')
    required=REQUIRED_SOURCES | {str(p.relative_to(source)) for p in (source/'src/specorganon').rglob('*.py')}
    if type(hashes) is not dict or not required <= hashes.keys():
        raise StudyHarnessError('registration omits required source bindings')
    for name, expected in hashes.items():
        if type(name) is not str: raise StudyHarnessError('source binding path must be text')
        parts = Path(name)
        if (parts.is_absolute() or '..' in parts.parts or type(expected) is not str
                or re.fullmatch('[0-9a-f]{64}', expected) is None
                or digest(_read(source / parts, 8_388_608)) != expected):
            raise StudyHarnessError('registered source changed: ' + name)
    for name in (value['protocol'], value['rubric'], value['mandate'], value['independent_review_receipt']):
        if type(name) is not str or name not in hashes:
            raise StudyHarnessError('protocol/rubric/review must have bound file bytes')
    cells = value.get('cells')
    if type(cells) is not list or len(cells) != 28:
        raise StudyHarnessError('fixed complete 28-cell population required')
    wanted = {(t, f, r, m) for t in ('routeplan','treemap') for f in ('codex','gemini')
              for r in (1,2) for m in ('N','S','T')}
    wanted |= {(t,f,1,'A') for t in ('routeplan','treemap') for f in ('codex','gemini')}
    seen = set(); ids = set()
    for cell in cells:
        if (type(cell) is not dict or set(cell) != {'id','task','family','repetition','method'}
                or type(cell['id']) is not str
                or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', cell['id']) is None
                or type(cell['repetition']) is not int):
            raise StudyHarnessError('invalid fixed cell identity')
        if any(type(cell[k]) is not str for k in ('task','family','method')):
            raise StudyHarnessError('invalid fixed cell categories')
        key = (cell['task'],cell['family'],cell['repetition'],cell['method'])
        if key not in wanted or key in seen or cell['id'] in ids:
            raise StudyHarnessError('missing/duplicated/replaced fixed cell')
        seen.add(key); ids.add(cell['id'])
    return value, digest(raw)


def common_request(role, contract, documents, instructions):
    value = {'schema':1,'role':role,'role_instructions':instructions,
             'documents':{'contract.md':contract, **documents}}
    render_prompt(canonical(value))
    return value


class BasicCell:
    """N/S/A routes, with common sealed code/tests and one final review."""
    def __init__(self, root, transport, *, method, task, contract, sdd_guide,
                 protocol_sha256, fixture_mode=False, rubric=''):
        if method not in {'N','S','A'} or task not in {'routeplan','treemap'}:
            raise StudyHarnessError('unsupported basic route')
        self.root = _safe(root); self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.transport = transport; self.method = method; self.task = task
        self.contract = contract; self.sdd = sdd_guide; self.fixture = fixture_mode
        self.rubric=rubric
        policy = {'schema':2,'method':method,'task':task,'contract_sha256':digest(contract.encode()),
                  'sdd_sha256':digest(sdd_guide.encode()),'protocol_sha256':protocol_sha256,
                  'rubric_sha256':digest(rubric.encode()),
                  'fixture_mode':fixture_mode}
        with self._lock():
            path = self.root/'policy.json'
            if path.exists() and _json(path) != policy: raise StudyHarnessError('cell binding changed')
            if not path.exists(): _write(path, policy)
            if not (self.root/'progress.json').exists():
                stages = []
                if method == 'S': stages = ['spec','design-tasks']
                if method == 'A': stages = [p.id for p in PHASES if p.id not in {'build','validate'}]
                stages += ['program','tests','measure']
                if method == 'A': stages += ['validate']
                stages += ['final-review']
                _write(self.root/'progress.json', {'schema':1,'stages':stages,'index':0,
                    'history':[],'process':{},'files':{},'measurements':[],'argv':None,'complete':False})

    @contextmanager
    def _lock(self):
        fd = os.open(self.root/'.lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
        try: fcntl.flock(fd, fcntl.LOCK_EX); yield
        finally: os.close(fd)

    def _request(self, state, stage):
        docs = {'process-documents.json':canonical(state['process']).decode(),
                'delivery-files.json':canonical(state['files']).decode(),
                'public-measurements.json':canonical(state['measurements']).decode(),
                'stage.txt':stage}
        if not self.fixture:
            for number, result in enumerate(state['measurements']):
                streams = {}
                for name in ('stdout','stderr'):
                    raw = _read(Path(result['test_job_ref']).parent/(name+'.bin'),2_097_152)
                    if digest(raw)!=result[name+'_sha256']:
                        raise StudyHarnessError('public measured stream changed')
                    text=raw.decode(errors='replace')
                    if encoded_contribution(text)>4000:
                        raise StudyHarnessError('common public stream input ceiling')
                    streams[name]=text
                docs['public-streams-'+str(number)+'.json']=canonical(streams).decode()
        instructions = ('Return schema=1, manifest={schema:1,steps:[]}, files={relative_path:complete_text}, '
            'reason. No approvals, engine mutations, claimed tests or reserved feedback. '
            'Only supplied actual measurements support execution claims. '
            'Code/files map has <=20000 encoded bytes; process <=6000 encoded bytes per stage. ')
        if stage == 'spec':
            docs['sdd-guide.md'] = self.sdd
            instructions += 'Before any code, return only SPEC.md with identified requirements/criteria from the fixed SDD guide.'
        elif stage == 'design-tasks':
            docs['sdd-guide.md'] = self.sdd
            instructions += 'Before any code, return only DESIGN.md and TASKS.md, tracing the already sealed SPEC.md.'
        elif stage in {p.id for p in PHASES}:
            phase = next(p for p in PHASES if p.id == stage)
            docs['phase-contract.json'] = canonical(phase.__dict__).decode()
            instructions += ('Ablation: propose substantive current phase reasoning as '+stage+'.md. '
                'Earlier documents are unaccepted drafts; no intermediate review or engine gate operates. '
                'Do not invent accepted phases, approvals, measurements or effects. '
                'Only return this markdown document. Explain assumptions, alternatives, trace links and limits as applicable.')
        elif stage == 'program':
            instructions += ('Return the complete '+self.task+'.py and README.md, optional standard-library helpers, '
                'no test files yet. README >=200 characters with installation, both public examples, formats/errors/limits/test command. '
                'For N the work process is your choice; optional process notes may be included in manifest.process_notes as text. '
                'For S follow the sealed SDD documents; for A follow your phase drafts. Do not change the public contract.')
        elif stage == 'tests':
            instructions += ('Program/README are sealed. Return ONLY new test_*.py files, using standard library unittest. '
                'Pertinent tests should detect plausible defects and exercise examples, limits and errors. '
                'Add manifest.test_argv as a nonempty explicit vector starting /opt/specorganon/venv/bin/python, '
                'delivery at /input/delivery readonly; /tmp scratch permitted. No invented passed/receipt.')
        elif stage == 'repair':
            instructions += ('The supplied first measurement actually failed. Return the COMPLETE changed delivery map '
                'and manifest.test_argv. Repair within contract; change executable Python bytes/argv before the second test. '
                'Original process documents remain sealed; explain deviations in reason. No third execution.')
        elif stage == 'final-review':
            docs['method.txt']=self.method
            docs['assessment-rubric.md']=self.rubric
            if self.method=='S': docs['sdd-guide.md']=self.sdd
            if self.method=='A': docs['phase-contracts.json']=canonical([p.__dict__ for p in PHASES]).decode()
            instructions = ('Independent FINAL review, once, no repairs afterwards. Judge public contract, delivery, '
                'substantive process adherence and only actual supplied public tests. Return schema=1, '
                'verdict accept/reject/inconclusive, nonempty reason, findings as array of nonempty objects, '
                'tests_executed=false. No reserved tests, expected outputs or results are supplied. '
                'Do not infer field benefits, comparative superiority or accepted engine phases from these files.')
            instructions += assessment_instructions(self.method)
        return common_request('review' if stage == 'final-review' else 'author', self.contract, docs, instructions)

    def _apply(self, state, stage, packet):
        if packet.get('provenance') != ('synthetic' if self.fixture else 'native'):
            raise StudyHarnessError('actual isolated role provenance required')
        response = validate_result(packet['result'], 'review' if stage=='final-review' else 'author')
        if stage == 'final-review':
            _write(self.root/'assessment.json',observe_assessment(response,self.method))
            state['final_review'] = response; state['complete'] = True
            return
        if response['manifest'].get('schema') != 1 or response['manifest'].get('steps') != []:
            raise StudyHarnessError('basic route cannot apply engine steps or approvals')
        files = response['files']
        for name in files: safe_file(name)
        if stage not in {'program','tests','repair'}:
            expected = {'SPEC.md'} if stage=='spec' else ({'DESIGN.md','TASKS.md'} if stage=='design-tasks' else {stage+'.md'})
            if set(files) != expected or any(not text.strip() for text in files.values()):
                raise StudyHarnessError('process stage files changed or missing')
            if encoded_contribution(files) > (12000 if stage=='design-tasks' else 6000):
                raise StudyHarnessError('process stage byte ceiling')
            state['process'].update(files)
        else:
            if stage=='program':
                if (self.task+'.py' not in files or len(files.get('README.md','').strip())<200
                        or any(Path(n).name.startswith('test_') for n in files)):
                    raise StudyHarnessError('program/README required before tests')
                notes = response['manifest'].get('process_notes')
                if notes is not None:
                    if self.method!='N' or type(notes) is not str or encoded_contribution(notes)>54000:
                        raise StudyHarnessError('invalid optional free-process notes')
                    state['process']['free-process.txt'] = notes
                candidate = files
            elif stage=='tests':
                if (not files or any(not Path(n).name.startswith('test_') or not n.endswith('.py') for n in files)
                        or files.keys() & state['files'].keys()):
                    raise StudyHarnessError('tests cannot replace sealed program/README')
                candidate = {**state['files'], **files}
            else:
                if self.task+'.py' not in files or len(files.get('README.md','').strip())<200:
                    raise StudyHarnessError('repair needs complete delivery')
                candidate = files
            if encoded_contribution(candidate)>20000: raise StudyHarnessError('common delivery byte ceiling')
            if stage in {'tests','repair'}:
                argv = response['manifest'].get('test_argv')
                if (type(argv) is not list or not argv or argv[0]!='/opt/specorganon/venv/bin/python'
                        or any(type(v) is not str or not v or '\0' in v for v in argv)):
                    raise StudyHarnessError('bounded explicit public test argv required')
                state['argv'] = argv
            state['files'] = candidate
        if encoded_contribution(state['process'])>54000:
            raise StudyHarnessError('common process document ceiling')

    def _step(self):
        with self._lock():
            state = _json(self.root/'progress.json')
            if state.get('terminal_failure'):
                return {'action':'failed','complete':False,'failure':state['terminal_failure']}
            if state['complete']:
                self.validate_closed(state)
                return {'action':'complete','classification':'synthetic' if self.fixture else 'native-cell'}
            stage = state['stages'][state['index']]
            job_id = 'step-'+str(state['index']+1).zfill(2)+'-'+stage
            # Input snapshot is durable before dispatch. Closed transport packets
            # are replayed on recovery; no new job ID is allocated for failures.
            if stage=='measure':
                result = self.transport.measure(job_id, state['argv'], state['files'])
                self.transport.verify_test({'test_job_ref':result['test_job_ref'],'argv':state['argv']},
                                           state['files'],require_passed=False)
                state['measurements'].append(result)
                if not result['passed'] and len(state['measurements'])==1:
                    state['stages'][state['index']+1:state['index']+1] = ['repair','measure']
                packet_sha = digest(canonical(result))
            else:
                request = self._request(state, stage)
                path = self.root/(job_id+'-request.json')
                if path.exists() and _json(path)!=request: raise StudyHarnessError('prepared request changed')
                if not path.exists(): _write(path,request)
                packet = self.transport.call(job_id,request['role'],request)
                if packet.get('request_sha256') != digest(canonical(request)):
                    raise StudyHarnessError('role request binding diverged')
                _write(self.root/(job_id+'-packet.json'),packet)
                self._apply(state,stage,packet); packet_sha=digest(canonical(packet))
            state['history'].append({'stage':stage,'job_id':job_id,'packet_sha256':packet_sha})
            state['index']+=1
            _write(self.root/'progress.json',state)
            return {'action':stage,'complete':state['complete']}

    def validate_closed(self,state):
        last=state['history'][-1]
        if last['stage']!='final-review': raise StudyHarnessError('completion lacks final review')
        packet=_json(self.root/(last['job_id']+'-packet.json'))
        request=_json(self.root/(last['job_id']+'-request.json'))
        if (digest(canonical(packet))!=last['packet_sha256']
                or packet['request_sha256']!=digest(canonical(request))
                or request['documents']['delivery-files.json']!=canonical(state['files']).decode()
                or request['documents']['process-documents.json']!=canonical(state['process']).decode()
                or packet['result']!=state['final_review']):
            raise StudyHarnessError('completed delivery differs from reviewed snapshot')

    def step(self):
        try: return self._step()
        except (StudyHarnessError,StudyBudgetError,NativeRoleError,DockerRoleError) as exc:
            # Start from the last committed snapshot, not a partially mutated
            # in-memory candidate. Native/raw packets stay in their journals.
            # Filesystem failures propagate for same-job recovery; they never
            # receive an invented model failure or a new call ID.
            with self._lock():
                state=_json(self.root/'progress.json')
                stage=state['stages'][state['index']] if state['index']<len(state['stages']) else 'closed_snapshot'
                failure={'status':'generation_failed','stage':stage,
                         'error_type':type(exc).__name__,'reason':str(exc),
                         'automatic_retry':False,'grade':None}
                state['terminal_failure']=failure
                _write(self.root/'progress.json',state)
                _write(self.root/'terminal-failure.json',failure)
                return {'action':'failed','complete':False,'failure':failure}


class ToolkitCell:
    """Real T engine/controller route plus the same one-time final review."""
    def __init__(self, root, transport, *, task, contract, mandate, protocol_sha256, rubric=''):
        if (task not in {'routeplan','treemap'} or type(protocol_sha256) is not str
                or re.fullmatch('[0-9a-f]{64}',protocol_sha256) is None):
            raise StudyHarnessError('explicit toolkit cell identity required')
        self.root=_safe(root); self.root.mkdir(parents=True,mode=0o700,exist_ok=True)
        self.transport=transport; self.contract=contract; self.mandate=mandate
        self.rubric=rubric
        policy={'schema':2,'task':task,'protocol_sha256':protocol_sha256,
                'rubric_sha256':digest(rubric.encode()),
                'contract_sha256':digest(contract.encode()),'mandate_sha256':digest(mandate.encode())}
        path=self.root/'toolkit-policy.json'
        if path.exists() and _json(path)!=policy: raise StudyHarnessError('toolkit cell identity changed')
        if not path.exists(): _write(path,policy)
        self.case=self.root/'case'
        if not self.case.exists():
            engine.create_case(self.case,'Registered '+task+' software cell','development',
                               'human:owner',approval_policy='local')
        # These are current reads before any controller case writes, as required
        # by the local skill. The label records the existing delegated mandate.
        state=engine.get_state(self.case)
        _write(self.root/'last-read-status.json',state)
        _write(self.root/'last-read-report.json',case_report(self.case))
        _write(self.root/'last-read-next-task.json',describe_task(state))
        self.controller=Controller(self.case,self.root/'controller',transport,
                                   contract=contract,mandate=mandate,executor=transport)

    def _step(self):
        path=self.root/'common-final-review.json'
        if path.exists():
            self.controller.package_gate()
            packet=_json(path);request=_json(self.root/'common-final-request.json')
            if (packet.get('provenance')!='native' or packet.get('request_sha256')!=digest(canonical(request))
                    or request['documents']['delivery-files.json']!=canonical(self.controller._files()).decode()):
                raise StudyHarnessError('completed toolkit delivery differs from final review')
            _write(self.root/'assessment.json',observe_assessment(packet['result'],'T'))
            return {'action':'complete','final_review':packet['result'],'nine_phase_package_allowed':True}
        result=self.controller.step()
        if result['action']!='complete': return result
        files=self.controller._files()
        state=engine.get_state(self.case)
        records={}
        for item in state['items'].values():
            if item['kind']=='test':
                # Engine state contains the current version of the sole sealed
                # test ID. Historical failed receipts stay in controller history;
                # they are not reinterpreted as tests of the final delivery.
                data=item['data']; self.transport.verify_test(data,files)
                records[item['id']]={'current_test_job_ref':data['test_job_ref'],
                                    'delivery_tree_sha256':digest(canonical(files))}
        records['all_public_attempts']=self.public_attempts(files)
        request=self.final_request(state,files,records)
        prepared=self.root/'common-final-request.json'
        if prepared.exists() and _json(prepared)!=request: raise StudyHarnessError('final snapshot changed')
        if not prepared.exists(): _write(prepared,request)
        packet=self.transport.call('common-final-review','review',request)
        if packet.get('provenance')!='native' or packet.get('request_sha256')!=digest(canonical(request)):
            raise StudyHarnessError('final native review provenance/binding invalid')
        validate_result(packet['result'],'review')
        _write(path,packet)
        _write(self.root/'assessment.json',observe_assessment(packet['result'],'T'))
        return {'action':'complete','nine_phase_package_allowed':result['package_allowed'],
                'final_review':packet['result']}

    def public_attempts(self,files):
        attempts={}
        for entry in _json(self.controller.root/'progress.json')['history']:
            if entry['action']!='test':continue
            measured=self.transport.test_record(entry['job_id'])
            data={'test_job_ref':measured['test_job_ref'],'argv':measured['subject_argv'],
                  'delivery_tree_sha256':measured['delivery_tree_sha256']}
            self.transport.verify_test(data,files,require_passed=False,require_current=False)
            if measured['delivery_tree_sha256']!=entry['source_files_sha256']:
                raise StudyHarnessError('historical measured test differs from sealed source snapshot')
            attempts[entry['job_id']]={'measurement':measured,
                'applies_to_current_delivery':measured['delivery_tree_sha256']==digest(canonical(files)),
                'receipt':_json(Path(measured['test_job_ref'])),
                'streams':self.controller._test_streams(measured['test_job_ref'],measured)}
        return attempts

    def step(self):
        terminal=self.root/'terminal-failure.json'
        if terminal.exists():return _json(terminal)
        try:return self._step()
        except (ControllerError,StudyBudgetError,StudyHarnessError,NativeRoleError,DockerRoleError,UncertainJob) as exc:
            result={'action':'failed','failure':{'error_type':type(exc).__name__,'reason':str(exc),
                    'automatic_retry':False,'grade':None}}
            _write(terminal,result)
            return result

    def final_request(self,state,files,records):
        return common_request('review',self.contract,{
            'assessment-rubric.md':self.rubric,
            'method.txt':'T','state.json':canonical(state).decode(),
            'delivery-files.json':canonical(files).decode(),
            'public-measurements.json':canonical(records).decode()},
            'One independent common FINAL review, no regeneration afterwards. Judge contract, useful README, '
            'pertinent code/tests, substantive nine accepted phases and valid traceability. Only supplied '
            'public measurements were executed; no reserved results or field benefit. Return schema=1, '
            'verdict accept/reject/inconclusive, nonempty reason, findings as array of objects, tests_executed=false.'
            +assessment_instructions('T'))


def main():
    from scripts.study_campaign import main as campaign_main
    return campaign_main()


if __name__=='__main__':
    try: main()
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr); raise SystemExit(2)
