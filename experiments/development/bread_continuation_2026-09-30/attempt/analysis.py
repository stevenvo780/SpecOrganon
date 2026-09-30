import sys, json, hashlib, math
from pathlib import Path

PDFS = {'source_lca.pdf': ('9d64c0538b76ebaa19af86fb7ec231243cb5e1272316105ad979cfb9b6de3a32',2212666), 'source_survey.pdf': ('61b3b63cc7b5748138335fa2eaebde2f4ab0e454750e4592582fb80a5043dcee',526604)}
EXPECTED = {
 'piece_mass':('source_lca.txt',6,'The total mass of the bread itself was 736 grams.'),
 'norway_wheat_share':('source_lca.txt',6,'an average of 65% of the wheat has been coming from Norway and the remaining 35% from Poland.'),
 'poland_wheat_share':('source_lca.txt',6,'the remaining 35% from Poland.'),
 'mill_electricity':('source_lca.txt',7,'129 kWh electricity per ton of flour produced.'),
 'wheat_refined_flour_mass_share':('source_lca.txt',7,'67.1% refined flour, 13.8% whole flour, 19.1% bran.'),
 'wheat_whole_flour_mass_share':('source_lca.txt',7,'67.1% refined flour, 13.8% whole flour, 19.1% bran.'),
 'wheat_bran_mass_share':('source_lca.txt',7,'67.1% refined flour, 13.8% whole flour, 19.1% bran.'),
 'wheat_refined_flour_economic_allocation':('source_lca.txt',7,'Refined flour 78.5%, whole flour 14.2%, bran 7.3%.'),
 'wheat_whole_flour_economic_allocation':('source_lca.txt',7,'Refined flour 78.5%, whole flour 14.2%, bran 7.3%.'),
 'wheat_bran_economic_allocation':('source_lca.txt',7,'Refined flour 78.5%, whole flour 14.2%, bran 7.3%.'),
 'mill_to_baker_distance':('source_lca.txt',8,'438 km on >32 tonne truck'),
 'bakery_electricity':('source_lca.txt',8,'0.297 kWh electricity and 0.115 kWh natural gas per bread'),
 'bakery_natural_gas':('source_lca.txt',8,'0.297 kWh electricity and 0.115 kWh natural gas per bread'),
 'bakery_bread_waste':('source_lca.txt',8,'Bakery waste                      3.3'),
 'retail_bread_waste':('source_lca.txt',8,'Retail waste                      11.4'),
 'consumer_bread_waste_estimate':('source_lca.txt',8,'Consumer waste                     8.2'),
 'survey_respondents':('source_survey.txt',4,'Total                              1000              100.0')}

def sha(b): return hashlib.sha256(b).hexdigest()
def norm(s): return ' '.join(s.split())
def mag(v,u,b,reason=None):
 d={'value':v,'unit':u,'base':b}
 if reason: d['reason']=reason
 return d
def main():
 try:
  if len(sys.argv)!=2: raise ValueError('usage: analysis.py INPUT_DIRECTORY')
  root=Path(sys.argv[1])
  if not root.is_dir(): raise ValueError('input directory does not exist')
  def readj(n): return json.loads((root/n).read_text(encoding='utf-8'))
  manifest=readj('source_manifest.json'); claims=readj('source_claims.json'); tab=readj('survey_table1.json'); tm=readj('text_manifest.json')
  files={x['visible_file']:x for x in manifest['files']}
  for n in ('source_claims.json','survey_table1.json','source_lca.pdf','source_survey.pdf'):
   if n not in files: raise ValueError('manifest missing '+n)
   b=(root/n).read_bytes(); f=files[n]
   if len(b)!=f['bytes'] or sha(b)!=f['sha256']: raise ValueError('manifest integrity failure: '+n)
  texts={}
  for n,pdf in [('source_lca.txt','source_lca.pdf'),('source_survey.txt','source_survey.pdf')]:
   rec=tm['records'][n]; raw=(root/n).read_bytes()
   if len(raw)!=rec['bytes'] or sha(raw)!=rec['sha256']: raise ValueError('text manifest integrity failure: '+n)
   if sha((root/pdf).read_bytes())!=rec['original_pdf_sha256']: raise ValueError('derived text PDF binding failure: '+n)
   texts[n]=raw.decode('utf-8')
  cs=claims['claims']
  if len(cs)!=17 or len(tab['categories'])!=7: raise ValueError('expected 17 claims and seven survey rows')
  audits=[]
  by={c['key']:c for c in cs}
  if set(by)!=set(EXPECTED): raise ValueError('claim keys do not match audit specification')
  for k,(fn,page,excerpt) in EXPECTED.items():
   pages=texts[fn].split('\f')
   if page>len(pages) or norm(excerpt) not in norm(pages[page-1]): raise ValueError('passage audit failed: '+k)
   c=by[k]; src='lca' if fn=='source_lca.txt' else 'survey'
   if c['source']!=src: raise ValueError('claim source mismatch: '+k)
   audits.append({'key':k,'transcribed_value':c['value'],'unit':c['unit'],'base':c['base'],'locator':c['locator'],'checked_excerpt':excerpt,'passage_match':True,'hash_check_separate':True})
  cats=tab['categories']; counts=[x['count'] for x in cats]
  if sum(counts)!=tab['reported_total'] or tab['reported_total']!=1000: raise ValueError('survey count total mismatch')
  if len({x['key'] for x in cats})!=7: raise ValueError('duplicate survey category')
  for x in cats:
   if x['key']=='do_not_know':
    if x['min_slices'] is not None or x['max_slices'] is not None: raise ValueError('unknown category must have null bounds')
   elif x['key']=='more_than_twelve':
    if x['min_slices']!=13 or x['max_slices'] is not None: raise ValueError('open category bounds mismatch')
   elif x['min_slices'] is None or x['max_slices'] is None or x['min_slices']>x['max_slices']: raise ValueError('closed category bounds invalid')
  # Table 1 cells are checked directly against the archived page, not inferred from the JSON hash.
  p4=texts['source_survey.txt'].split('\f')[3]
  if 'Zero slices                            429               42.9' not in p4 or 'More than 12 slices                        19                1.9' not in p4 or 'Do not know                              33                3.3' not in p4: raise ValueError('survey Table 1 passage audit failed')
  total=tab['reported_total']; unknown=next(x['count'] for x in cats if x['key']=='do_not_know'); op=next(x['count'] for x in cats if x['key']=='more_than_twelve')
  known=total-unknown; closed=known-op
  low=sum(x['count']*x['min_slices'] for x in cats if x['min_slices'] is not None)
  known_low=low
  cl=[x for x in cats if x['key'] not in ('do_not_know','more_than_twelve')]
  cllow=sum(x['count']*x['min_slices'] for x in cl); clhigh=sum(x['count']*x['max_slices'] for x in cl)
  fl=lambda a,b:a/b
  inp=1000.0; masses={'refined_flour':671.0,'whole_flour':138.0,'bran':191.0}; outsum=sum(masses.values())
  piece=.736; e=.297/piece; g=.115/piece
  audit={'claims':audits,'table1_passage_check':{'locator':'source_survey.pdf, PDF/printed page 4, Table 1','checked_excerpts':['Zero slices                            429               42.9','More than 12 slices                        19                1.9','Do not know                              33                3.3'],'match':True},'prose_table_discrepancy':{'locator':'source_survey.pdf PDF page 3 section 3 versus PDF page 4 Table 1','prose_excerpt':'categories ranging from 0, 1–3, 4–6, 7–10, and more than 10 per week','table_excerpt':'Zero; 1–3; 4–6; 7–9; 10–12; More than 12; Do not know','finding':'interval boundaries differ (prose 7–10/>10; table 7–9, 10–12, >12); calculations use Table 1','status':'reported discrepancy; no resolution asserted'},'passage_audit_distinct_from_hash':True}
  result={'milling':{'wheat_input':mag(inp,'kg wheat','Proposed normalization: 1 metric tonne wheat input; 1000 kg.'),'outputs':{k:mag(v,'kg','Derived from 1000 kg wheat input multiplied by Table 3 wheat mass fraction.') for k,v in masses.items()},'outputs_sum':mag(outsum,'kg','Sum of three wheat milling outputs on the 1000 kg input basis.'),'balance_residual':mag(inp-outsum,'kg','Wheat input minus sum of listed outputs; excludes unreported process flows by construction.'),'economic_allocation':{k:mag(v,'%','Reported economic allocation factor for wheat milling inventory; distinct from mass fraction.') for k,v in [('refined_flour',78.5),('whole_flour',14.2),('bran',7.3)]},'mill_electricity':mag(129,'kWh/t_flour','Reported mill electricity per tonne flour produced; retained on original denominator, not converted to wheat input.')},'baking_energy':{'piece_mass':mag(piece,'kg','Reported 736 g baked loaf; converted g/1000.'),'electricity_per_kg':mag(e,'kWh/kg_bread','Reported 0.297 kWh/piece divided by 0.736 kg/piece.'),'natural_gas_per_kg':mag(g,'kWh/kg_bread','Reported 0.115 kWh/piece divided by 0.736 kg/piece.'),'sum_per_kg':mag(e+g,'kWh/kg_bread','Sum of electricity and natural gas normalized per kg baked bread; energy carriers remain separately reported.'),'original_per_piece':{'electricity':mag(.297,'kWh/piece','One studied commercial loaf.'),'natural_gas':mag(.115,'kWh/piece','One studied commercial loaf.'),'formula':'per kg = per piece / 0.736 kg per piece'}},'survey':{'total_respondents':mag(total,'respondents','All Table 1 respondents.'),'known_respondents':mag(known,'respondents','Total less do-not-know responses.'),'unknown_respondents':mag(unknown,'respondents','Do not know category; not treated as observed zero.'),'open_category_respondents':mag(op,'respondents','More than 12 slices category; lower bound 13 under whole-slice interpretation, no finite upper bound.'),'closed_category_respondents':mag(closed,'respondents','Known responses excluding open >12 category; denominator for closed interval.'),'lower_bound_total_all':mag(low,'slices/week','Sum of category minima; unknown responses contribute no identified amount and zero only for conservative lower-bound arithmetic.'),'lower_bound_total_known':mag(known_low,'slices/week','Known-response category minima; open category contributes minimum 13.'),'closed_total_interval':{'lower':mag(cllow,'slices/week','Closed categories only; excludes unknown and open responses.'),'upper':mag(clhigh,'slices/week','Closed categories only; assumes each integer slice count may take its category maximum.')},'lower_bound_mean_all':mag(fl(low,total),'slices/household/week','Lower-bound sum divided by all 1000 respondents; unknowns are not observed zeros.'),'lower_bound_mean_known':mag(fl(known_low,known),'slices/household/week','Lower-bound sum divided by 967 known responses.'),'closed_mean_interval':{'lower':mag(fl(cllow,closed),'slices/household/week','Closed-category lower total divided by 948 closed responses.'),'upper':mag(fl(clhigh,closed),'slices/household/week','Closed-category upper total divided by 948 closed responses.')},'finite_upper_bound_all':False,'finite_upper_bound_known':False,'interpretation':'Table categories imply integer slice counts; open >12 is bounded below by 13 but unbounded above. Do-not-know is missing amount, never an observed zero. All/known lower bounds use zero contribution for unknown only as a conservative bound, with distinct denominators; no conversion to mass or intake.'},'source_audit':audit,'not_identified':{'slice_mass_kg':{'value':None,'unit':'kg/slice','base':'Survey households','reason':'No slice mass measured or supplied.'},'survey_to_lca_product_link':{'value':None,'unit':'not identifiable','base':'Different study populations/products','reason':'No identified purchasers or linkage between survey households and LCA product.'},'causal_packaging_effect':{'value':None,'unit':'not identifiable','base':'No intervention comparison in these articles','reason':'Archived LCA inventory and self-report survey do not estimate causal effect of proposed packaging.'}}}
  # JSON encoder with allow_nan=False guarantees finite JSON values.
  sys.stdout.write(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
 except Exception as exc:
  print('analysis error: '+str(exc),file=sys.stderr); raise SystemExit(2)
if __name__=='__main__': main()
