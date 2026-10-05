"""Prepare a fixed design before any v3 output; not a registration/admission."""
from pathlib import Path
from itertools import permutations
import random, hashlib, json, datetime, uuid

root=Path(__file__).parent
assert not (root/'schedule-private.json').exists(), 'do not replace opaque mapping'
seed=731
rng=random.Random(seed)
orders=list(permutations('NST'))*2
rng.shuffle(orders)
ablation_positions=['before_T']*3+['after_T']*3
rng.shuffle(ablation_positions)
blocks=[(task,family,rep) for task in ['FractionMix','PolicyPick','ListPatch']
        for family in ['codex','gemini'] for rep in [1,2]]
rows=[]
block_records=[]
ablation_index=0
for block_index,((task,family,rep),order) in enumerate(zip(blocks,orders),1):
    sequence=list(order)
    position=None
    if rep==1:
        position=ablation_positions[ablation_index]; ablation_index+=1
        sequence.insert(sequence.index('T')+(position=='after_T'),'A')
    block_id=f'block-{block_index:02d}'
    block_records.append({'block_id':block_id,'task':task,'family':family,'rep':rep,
                          'main_order':list(order),'sequence':sequence,'ablation_position':position})
    for method in sequence:
        rows.append({'sequence':len(rows)+1,'block_id':block_id,'task':task,'family':family,
                     'rep':rep,'method':method,'opaque_delivery_id':'delivery-'+uuid.uuid4().hex,
                     'author':{'provider':family,'model':'gpt-6.1-sol' if family=='codex' else 'Gemini 3.8 Flash (Medium)',
                               'effort':'medium'},
                     'reviewer':{'provider':'gemini' if family=='codex' else 'codex',
                                 'model':'Gemini 3.8 Flash (Medium)' if family=='codex' else 'gpt-6.1-sol',
                                 'effort':'medium'},
                     'limits':{'max_calls':40,'max_elapsed_seconds':6000,'max_total_input_bytes':3145728}})
assert len(rows)==42 and ablation_index==6
assert len({(r['task'],r['family'],r['rep'],r['method']) for r in rows})==42
assert len({r['opaque_delivery_id'] for r in rows})==42
assert all(sum(tuple(b['main_order'])==p for b in block_records)==2 for p in permutations('NST'))
assert sum(b['ablation_position']=='before_T' for b in block_records)==3
assert sum(b['ablation_position']=='after_T' for b in block_records)==3
record={'schema':1,'identity':'software-comparison-v3','status':'draft_fixed_schedule_not_registered',
        'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scheduler_seed':seed,
        'model_seed':'not controlled','native_author_calls':0,'registered':False,
        'blocks':block_records,'rows':rows}
raw=(json.dumps(record,indent=2,ensure_ascii=False)+'\n').encode()
path=root/'schedule-private.json'; path.write_bytes(raw); path.chmod(0o600)
public={k:v for k,v in record.items() if k!='rows'}
public.update({'cells':42,'main_cells':36,'ablation_cells':6,
               'private_mapping_sha256':hashlib.sha256(raw).hexdigest(),
               'custody':'opaque delivery mapping retained privately; not author/reviewer input',
               'schedule_controls_passed':True,'remaining_before_registration':[
                   'definitive contracts and sixty recipes per task', 'N/S/T/A harnesses',
                   'rubrics and analysis', 'execution and isolation controls',
                   'independent full accepted review', 'immutable source/image registration'],
               'full_goal_completed':False})
(root/'schedule-public.json').write_text(json.dumps(public,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'cells':42,'blocks':12,'main_orders_each':2,'ablations_before_T':3,
                  'ablations_after_T':3,'native_author_calls':0,'registered':False}))
