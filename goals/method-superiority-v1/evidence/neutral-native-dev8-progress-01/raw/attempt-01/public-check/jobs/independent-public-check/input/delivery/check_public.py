"""Public development checks independent of generated tests; no reserved score.

Oracle for small intervals uses integer-cell occupancy instead of interval merge.
This corpus is derived from the public contract. It is not a holdout comparison.
"""
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys


def oracle(intervals):
    cells=sorted({x for lo,hi in intervals for x in range(lo,hi)})
    merged=[]
    for x in cells:
        if merged and merged[-1][1]==x: merged[-1][1]=x+1
        else: merged.append([x,x+1])
    return {'merged':merged,'covered':len(cells),
        'span':[cells[0],cells[-1]+1] if cells else None,
        'gaps':[[a[1],b[0]] for a,b in zip(merged,merged[1:])]}


def equal(a,b):
    if type(a) is not type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return a==b


def no_duplicates(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('duplicate output key')
        result[k]=v
    return result


def cases():
    corpus=[]
    def valid(name,requests,expected=None):
        raw=b''.join((json.dumps({'intervals':r},separators=(',',':'))+'\n').encode() for r in requests)
        corpus.append((name,raw,[oracle(r) for r in requests] if expected is None else expected))
    valid('empty-input',[])
    examples=[[[1,3],[3,7],[10,12]],[[4,8],[1,2],[2,6],[4,8]],[],[[-5,-2],[0,1]]]
    for i,example in enumerate(examples):valid('public-example-'+str(i+1),[example])
    valid('public-examples-batch',examples)
    rng=random.Random(20261006)
    for i in range(80):
        requests=[]
        for _ in range(rng.randrange(1,5)):
            intervals=[]
            for _ in range(rng.randrange(21)):
                lo=rng.randrange(-20,20);hi=rng.randrange(lo+1,21)
                intervals.append([lo,hi])
            requests.append(intervals)
        valid('cell-occupancy-'+str(i),requests)
    empty={'merged':[],'covered':0,'span':None,'gaps':[]}
    valid('pair-limit-2000',[[[0,1]]*2000],[{'merged':[[0,1]],'covered':1,'span':[0,1],'gaps':[]}])
    limit=10**12
    valid('integer-boundary',[[[-limit,0],[0,limit]]],[{'merged':[[-limit,limit]],'covered':2*limit,'span':[-limit,limit],'gaps':[]}])
    base=b'{"intervals":[]}\n'
    corpus.append(('byte-limit-exact',b' '*(131072-len(base))+base,[empty]))
    invalid=[b'\n',b' \n',b'{}\n',b'[]\n',b'{"intervals":null}\n',b'{"intervals":[],"extra":0}\n',
        b'{"intervals":[],"intervals":[]}\n',b'{"intervals":[[0,0]]}\n',b'{"intervals":[[2,1]]}\n',
        b'{"intervals":[[false,1]]}\n',b'{"intervals":[[0,1.0]]}\n',b'{"intervals":[[0,1,2]]}\n',
        b'{"intervals":[[0,1000000000001]]}\n',b'{"intervals":[[-1000000000001,0]]}\n',
        b'\xff\n',b'{"intervals":[[0,NaN]]}\n',b'{"intervals":[[0,Infinity]]}\n',b'{',
        json.dumps({'intervals':[[0,1]]*2001}).encode()+b'\n',
        b' '*(131073-len(base))+base]
    for i,raw in enumerate(invalid):corpus.append(('invalid-'+str(i),raw,None))
    for i,bad in enumerate([b'\n',b'{}\n',b'\xff\n']):
        corpus.append(('atomic-after-valid-'+str(i),base+bad,None))
        corpus.append(('atomic-before-valid-'+str(i),bad+base,None))
    return corpus


def main():
    target=Path(__file__).with_name('range_audit.py');records=[]
    for name,raw,expected in cases():
        p=subprocess.run([sys.executable,str(target)],input=raw,capture_output=True,timeout=4)
        if expected is None:
            passed=p.returncode==2 and p.stdout==b'' and p.stderr==b'range-audit: invalid input\n'
        else:
            try:
                lines=p.stdout.decode('utf-8').splitlines()
                observed=[json.loads(line,object_pairs_hook=no_duplicates) for line in lines]
                passed=p.returncode==0 and p.stderr==b'' and equal(observed,expected)
                passed=passed and (p.stdout==b'' if not expected else p.stdout.endswith(b'\n'))
            except (ValueError,UnicodeError):passed=False
        records.append({'name':name,'passed':passed,'exit_code':p.returncode,
            'input_sha256':hashlib.sha256(raw).hexdigest(),'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),
            'stderr_sha256':hashlib.sha256(p.stderr).hexdigest()})
    failed=[r for r in records if not r['passed']]
    print(json.dumps({'classification':'independent public development checks; not reserved method comparison',
        'cases':len(records),'passed':sum(r['passed'] for r in records),'failed':failed,
        'observations_sha256':hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest(),
        'oracle':'integer-cell occupancy for small intervals; explicit public boundary expectations'}))
    return bool(failed)


if __name__=='__main__':sys.exit(main())
