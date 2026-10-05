"""Typed rubric observations, separate from functional outcomes or approval.

A missing/malformed judgment stays inconclusive. No high code score imputes
process adherence and no rubric sum certifies nine accepted engine phases.
"""
from specorganon.role_jobs import canonical, digest


class AssessmentError(ValueError):
    pass


def rubric_ids(method):
    if method not in {'N','S','T','A'}: raise AssessmentError('unknown method rubric')
    count={'N':0,'S':8,'T':9,'A':9}[method]
    return {'documentation':['D'+str(i) for i in range(1,11)],
            'common':['C'+str(i) for i in range(1,7)],
            'adherence':[method+str(i) for i in range(1,count+1)]}


def instructions(method):
    ids=rubric_ids(method)
    return (' Also return assessment as an object with exactly documentation,common,adherence arrays. '
        'Required IDs are '+canonical(ids).decode()+'. Each array contains every ID once, as '
        '{id,verdict,locator,reason}; verdict is satisfied/unsatisfied/inconclusive. '
        'Use concrete file/line or supplied-state artifact locators and a short reason. '
        'For absent evidence use locator absent:<artifact> and unsatisfied or inconclusive, never satisfied. '
        'N has adherence=[]; no process is mandatory for free work. Judge SDD and ablation drafts by their '
        'prescribed purposes/precedence, never invent engine acceptance. T points require the supplied '
        'current accepted phase and its native review/trace/test evidence. Only supplied actual receipts '
        'support execution claims. Tests_executed=false remains mandatory; these are text judgments, '
        'not executions, field impact, causal attribution or a combined winner score.')


def validate(value,method):
    expected=rubric_ids(method)
    if type(value) is not dict or set(value)!=set(expected):
        raise AssessmentError('rubric dimensions missing or changed')
    normalized={}
    for name,ids in expected.items():
        rows=value[name]
        if type(rows) is not list or len(rows)!=len(ids): raise AssessmentError('rubric point count changed')
        by_id={}
        for row in rows:
            if (type(row) is not dict or set(row)!={'id','verdict','locator','reason'}
                    or type(row['id']) is not str or row['id'] not in ids or row['id'] in by_id
                    or type(row['verdict']) is not str
                    or row['verdict'] not in {'satisfied','unsatisfied','inconclusive'}
                    or any(type(row[k]) is not str or not row[k].strip() for k in ('locator','reason'))):
                raise AssessmentError('rubric point must have unique ID, status, evidence locator and reason')
            if row['verdict']=='satisfied' and row['locator'].startswith('absent:'):
                raise AssessmentError('absent evidence cannot satisfy rubric')
            by_id[row['id']]=row
        normalized[name]=[by_id[id] for id in ids]
    return normalized


def summarize(value,method):
    rows=validate(value,method); summary={}
    for name,points in rows.items():
        counts={status:sum(p['verdict']==status for p in points)
                for status in ('satisfied','unsatisfied','inconclusive')}
        summary[name]={**counts,'denominator':len(points),
                       'status':'not_applicable' if not points else 'observed',
                       'points':points}
    return {'dimensions':summary,'judgment_sha256':digest(canonical(rows)),
            'combined_score':None,'functional_score':None,'causal_verdict':None}


def observe(result,method):
    """Record an independent result without retries or inferred rubric scores."""
    try:
        if result.get('tests_executed') is not False:
            raise AssessmentError('text-only reviewer may not claim its own test execution')
        return {'status':'observed',**summarize(result.get('assessment'),method)}
    except (AssessmentError,TypeError,AttributeError) as exc:
        return {'status':'inconclusive','reason':str(exc),'judgment':result.get('assessment') if type(result) is dict else None,
                'dimensions':None,'combined_score':None,'functional_score':None,'causal_verdict':None}
