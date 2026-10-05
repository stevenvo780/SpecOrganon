"""Durable common/campaign admission and reserved-evaluation prerequisite.

Inert infrastructure: construction is not registration or native admission. The
caller must validate full immutable registration and current original quotas.
The trusted transport reconciles existing handles; never generate a replacement.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import time

from specorganon.role_jobs import JobStore, canonical, digest, _json, _write, _safe, _read
from specorganon.software_controller import executable_fingerprint
from scripts.controller_native_role import render_prompt

CELL_LIMITS = {'calls': 40, 'input_bytes': 3145728, 'seconds': 6000, 'tests': 2}
CAMPAIGN_LIMITS = {'calls': 1680, 'input_bytes': 132120576, 'seconds': 252000, 'cells': 42}
TERMINAL = ('complete', 'generation_failed', 'infra_inconclusive')


class BudgetError(ValueError):
    pass


class ClockUnknown(ValueError):
    pass


def identifier(value):
    if type(value) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value):
        raise BudgetError('bounded persistent identity required')
    return value


def sha256(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise BudgetError('immutable SHA256 required')
    return value


class RunJournal:
    def __init__(self, root, *, registration_sha256, cells, validate_registration, validate_quota):
        self.root = _safe(root); self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.root.stat().st_uid != os.geteuid() or self.root.stat().st_mode & 0o022:
            raise BudgetError('private owned journal required')
        if not callable(validate_registration) or not callable(validate_quota):
            raise BudgetError('source and quota validators are mandatory')
        self.registration = validate_registration; self.quota = validate_quota
        if (type(cells) is not list or len(cells) != 42 or
                any(type(c) is not dict or set(c) != {'id', 'method'} for c in cells)):
            raise BudgetError('complete fixed42 population required')
        for cell in cells:
            identifier(cell['id'])
            if cell['method'] not in ('N', 'S', 'T', 'A'): raise BudgetError('unknown method')
        if len({c['id'] for c in cells}) != 42 or {m:sum(c['method']==m for c in cells) for m in 'NSTA'} != {'N':12,'S':12,'T':12,'A':6}:
            raise BudgetError('fixed36main+6ablation population required')
        self.policy = {'schema': 1, 'registration_sha256': sha256(registration_sha256),
                       'source_sha256': digest(_read(Path(__file__), 128000)), 'cells': cells,
                       'cell_limits': CELL_LIMITS, 'campaign_limits': CAMPAIGN_LIMITS}
        with self.lock():
            path = self.root/'policy.json'
            if path.exists() and _json(path) != self.policy: raise BudgetError('registration/source/order/budget changed')
            if not path.exists(): _write(path, self.policy)
            if not (self.root/'progress.json').exists():
                _write(self.root/'progress.json', {'schema':1,'global_clock':None,'evaluation':None,
                    'cells':{c['id']:{'clock':None,'roles':{},'tests':{},'terminal':None} for c in cells}})

    @contextmanager
    def lock(self):
        fd = os.open(self.root/'.lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
        try: fcntl.flock(fd, fcntl.LOCK_EX); yield
        finally: os.close(fd)

    @staticmethod
    def elapsed(anchor):
        if anchor is None: return 0
        if anchor['boot_id_sha256'] != JobStore._boot_id():
            raise ClockUnknown('monotonic continuity unknown; no reset or new admission')
        value = time.monotonic()-anchor['monotonic']
        if value < 0: raise ClockUnknown('monotonic clock moved backward')
        return value

    @staticmethod
    def anchor():
        return {'epoch':time.time(),'monotonic':time.monotonic(),'boot_id_sha256':JobStore._boot_id()}

    def _cell(self, state, identity):
        if identity not in state['cells']: raise BudgetError('unregistered cell')
        return state['cells'][identity]

    def validate(self):
        result = self.registration()
        if (type(result) is not dict or result.get('registration_sha256') != self.policy['registration_sha256']
                or _json(self.root/'policy.json') != self.policy):
            raise BudgetError('full immutable registration/source validation or policy differs')

    def admit(self, cell_id, job_id, kind, binding):
        identifier(job_id)
        if kind not in ('roles','tests') or type(binding) is not dict:
            raise BudgetError('invalid admission kind')
        with self.lock():
            self.validate()
            state = _json(self.root/'progress.json'); cell = self._cell(state, cell_id)
            if cell['terminal'] is not None or state['evaluation'] is not None:
                raise BudgetError('sealed cell/evaluation cannot dispatch even an old handle')
            existing = cell[kind].get(job_id)
            if existing is not None:
                if existing['binding'] != binding: raise BudgetError('existing job input changed; no replacement')
                # Only reconciliation of this same admitted handle is permitted.
                # Immutable-source checking still runs; quota/deadline is not renewed.
                return existing
            next_cell = next((c['id'] for c in self.policy['cells'] if state['cells'][c['id']]['terminal'] is None), None)
            if next_cell != cell_id: raise BudgetError('fixed sequential order required')
            duration = 180 if kind == 'roles' else 120
            if (self.elapsed(state['global_clock']) + duration > CAMPAIGN_LIMITS['seconds'] or
                    self.elapsed(cell['clock']) + duration > CELL_LIMITS['seconds']):
                raise BudgetError('deadline has insufficient remaining execution window')
            roles = list(cell['roles'].values())
            all_roles = [r for c in state['cells'].values() for r in c['roles'].values()]
            if kind == 'roles':
                size = binding.get('rendered_input_bytes')
                if type(size) is not int or not 1 <= size <= 128000: raise BudgetError('rendered input bound required')
                if len(roles) >= CELL_LIMITS['calls'] or len(all_roles) >= CAMPAIGN_LIMITS['calls']:
                    raise BudgetError('native call ceiling exhausted')
                if (sum(r['binding']['rendered_input_bytes'] for r in roles)+size > CELL_LIMITS['input_bytes'] or
                        sum(r['binding']['rendered_input_bytes'] for r in all_roles)+size > CAMPAIGN_LIMITS['input_bytes']):
                    raise BudgetError('cumulative rendered input ceiling exhausted')
            else:
                history = sorted(cell['tests'].values(), key=lambda r:r['sequence'])
                if len(history) >= 2: raise BudgetError('two-test ceiling exhausted')
                if history:
                    previous = history[-1]
                    outcome = previous['outcome']
                    rejected = any(r['outcome'] and r['outcome'].get('review_verdict')=='reject'
                                   and r['binding'].get('delivery_sha256')==previous['binding']['delivery_sha256'] for r in roles)
                    if not outcome or not (outcome.get('test_passed') is False or rejected):
                        raise BudgetError('second test needs actual first failure or source-bound semantic rejection')
                    if previous['binding']['executable_sha256']==binding['executable_sha256']:
                        raise BudgetError('second test requires executable bytes/argv change')
            observation = self.quota()  # Only fresh admissions need current capacity evidence.
            if (self.elapsed(state['global_clock']) + duration > CAMPAIGN_LIMITS['seconds'] or
                    self.elapsed(cell['clock']) + duration > CELL_LIMITS['seconds']):
                raise BudgetError('deadline exhausted during quota observation')
            if state['global_clock'] is None: state['global_clock'] = self.anchor()
            if cell['clock'] is None: cell['clock'] = self.anchor()
            entry = {'sequence':len(cell[kind])+1,'binding':binding,'outcome':None,'quota_observation':observation}
            cell[kind][job_id] = entry
            _write(self.root/'progress.json', state)  # Consumption precedes dispatch, no refund on failure.
            return entry

    def outcome(self, cell_id, job_id, kind, value):
        with self.lock():
            state = _json(self.root/'progress.json'); entry = self._cell(state, cell_id)[kind][job_id]
            if entry['outcome'] is not None and entry['outcome'] != value: raise BudgetError('closed execution outcome changed')
            entry['outcome'] = value; _write(self.root/'progress.json',state)

    def close_cell(self, cell_id, *, status, delivery_sha256):
        if status not in TERMINAL: raise BudgetError('generation terminal status required')
        with self.lock():
            self.validate(); state = _json(self.root/'progress.json'); cell = self._cell(state,cell_id)
            seal = {'status':status,'delivery_sha256':sha256(delivery_sha256),
                    'admissions_sha256':digest(canonical({'roles':cell['roles'],'tests':cell['tests']}))}
            if cell['terminal'] is not None:
                if any(cell['terminal'][k]!=v for k,v in seal.items()): raise BudgetError('closed cell changed')
                return cell['terminal']
            if cell['clock'] is None: raise BudgetError('unadmitted row is not a completed generation')
            if any(r['outcome'] is None for kind in ('roles','tests') for r in cell[kind].values()):
                raise BudgetError('uncertain admitted execution must be reconciled before closure')
            seal['elapsed_seconds'] = self.elapsed(cell['clock'])
            seal['campaign_elapsed_seconds'] = self.elapsed(state['global_clock'])
            if status == 'complete' and (seal['elapsed_seconds'] > CELL_LIMITS['seconds']
                    or seal['campaign_elapsed_seconds'] > CAMPAIGN_LIMITS['seconds']):
                raise BudgetError('generation completed beyond original cell/campaign deadline')
            cell['terminal'] = seal; _write(self.root/'progress.json',state)
            return seal

    def evaluation_gate(self, verify_milestone):
        """Seal decision only after42closed; callback verifies each fixedT physically.

        This journal cannot itself prove nine phases. Full native receipt/current
        engine/substantive audit validation is required of the registered verifier.
        """
        if not callable(verify_milestone): raise BudgetError('actual milestone verifier required')
        with self.lock():
            self.validate(); state = _json(self.root/'progress.json')
            if any(c['terminal'] is None for c in state['cells'].values()):
                raise BudgetError('all42generations must close; no reserved feedback early')
            seals = {i:c['terminal'] for i,c in state['cells'].items()}
            seal_sha = digest(canonical(seals))
            if state['evaluation'] is not None:
                if state['evaluation']['generation_seals_sha256']!=seal_sha: raise BudgetError('terminal snapshots changed')
                return state['evaluation']
            proofs = {}
            fixed_t = [c['id'] for c in self.policy['cells'] if c['method']=='T']
            for identity in fixed_t:
                result = verify_milestone(identity, seals[identity])
                if (type(result) is not dict or set(result)!={'status','evidence_sha256'} or
                        result['status'] not in ('eligible','failed','inconclusive')):
                    raise BudgetError('invalid actual milestone verification result')
                sha256(result['evidence_sha256']); proofs[identity] = result
            eligible = [i for i in fixed_t if proofs[i]['status']=='eligible']
            if any(p['status']=='inconclusive' for p in proofs.values()):
                return {'schema':1,'status':'prerequisite_inconclusive','generation_seals_sha256':seal_sha,
                        'primary_T':fixed_t[0],'eligible_T':eligible,'all_fixed_T_proofs':proofs,
                        'reserved_evaluation_allowed':False,'new_cohort_authorized':False}
            decision = {'schema':1,'status':'released_once' if eligible else 'not_evaluated_by_prerequisite',
                        'generation_seals_sha256':seal_sha,'primary_T':fixed_t[0],
                        'eligible_T':eligible,'all_fixed_T_proofs':proofs,
                        'reserved_evaluation_allowed':bool(eligible),'new_cohort_authorized':False}
            state['evaluation'] = decision; _write(self.root/'progress.json',state)
            return decision

    def summary(self):
        with self.lock():
            state = _json(self.root/'progress.json')
            roles = [r for c in state['cells'].values() for r in c['roles'].values()]
            return {'admitted_native_jobs':len(roles),'rendered_input_bytes':sum(r['binding']['rendered_input_bytes'] for r in roles),
                    'admitted_tests':sum(len(c['tests']) for c in state['cells'].values()),
                    'terminal_cells':sum(c['terminal'] is not None for c in state['cells'].values()),
                    'evaluation':state['evaluation'],'native_tokens':None,'monetary_cost':None}


class RoleBudget:
    """Same interface as DockerRoles, shared by all treatments including auditors."""
    def __init__(self, journal, cell_id, transport):
        self.journal=journal; self.cell_id=cell_id; self.transport=transport

    def call(self, job_id, role, request):
        if type(request) is not dict or role not in ('author','review') or request.get('role') != role: raise BudgetError('role/request differs')
        _, text = render_prompt(canonical(request))
        binding = {'role':role,'request_sha256':digest(canonical(request)), 'rendered_input_bytes':len(text.encode())}
        delivery = request.get('documents',{}).get('delivery-files.json')
        if type(delivery) is str:
            from specorganon.ledger import strict_json_loads
            binding['delivery_sha256'] = digest(canonical(strict_json_loads(delivery)))
        self.journal.admit(self.cell_id,job_id,'roles',binding)
        packet = self.transport.call(job_id,role,request)
        if (type(packet) is not dict or type(packet.get('result')) is not dict
                or packet.get('request_sha256') != binding['request_sha256']):
            raise BudgetError('native request/result binding differs')
        self.journal.outcome(self.cell_id,job_id,'roles',{'packet_sha256':digest(canonical(packet)),
            'review_verdict':packet.get('result',{}).get('verdict') if role=='review' else None})
        return packet

    def measure(self, job_id, argv, files):
        binding = {'argv':argv,'delivery_sha256':digest(canonical(files)), 'executable_sha256':executable_fingerprint(files,argv)}
        self.journal.admit(self.cell_id,job_id,'tests',binding)
        value = self.transport.measure(job_id,argv,files)
        self.transport.verify_test({'test_job_ref':value['test_job_ref'],'argv':argv},files,require_passed=False)
        self.journal.outcome(self.cell_id,job_id,'tests',{'measurement_sha256':digest(canonical(value)),'test_passed':value['passed']})
        return value

    def verify_test(self,*args,**kwargs): return self.transport.verify_test(*args,**kwargs)
    def test_record(self,job_id): return _json(self.transport.root/'jobs'/identifier(job_id)/'measured-test.json')
