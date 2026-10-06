import argparse
import json
import statistics
import sys
import hashlib
import itertools
import math
from pathlib import Path

def median(lst): return statistics.median(lst) if lst else None
def mean(lst): return statistics.mean(lst) if lst else None
def rng(lst): return (min(lst), max(lst)) if lst else (None,None)

def extract_usage(receipt):
    if not receipt or not receipt.get('usage'):
        return {'input_tokens': None, 'output_tokens': None, 'cached_input_tokens': None, 'complete': False}
    last = receipt['usage'][-1]
    it = last.get('input_tokens')
    ot = last.get('output_tokens')
    cit = last.get('cached_input_tokens')
    if cit is None and 'prompt_tokens_details' in last:
        cit = last['prompt_tokens_details'].get('cached_tokens')
    if it is None: it = last.get('prompt_tokens')
    if ot is None: ot = last.get('completion_tokens')
    complete = (it is not None and ot is not None)
    return {'input_tokens': it, 'output_tokens': ot, 'cached_input_tokens': cit, 'complete': complete}

def summarize_resources(stage_data, arm):
    author = stage_data['author']
    method = stage_data.get('method')
    review = stage_data['review']
    
    if arm == 'T' and method is None:
        raise RuntimeError("T arm missing method")
        
    auth_dur = author.get('duration_seconds') if author else None
    meth_dur = method.get('duration_seconds') if method else (0 if arm in ('N', 'S') else None)
    rev_dur = review.get('duration_seconds') if review else None
    
    tot_dur = None
    if auth_dur is not None and rev_dur is not None and meth_dur is not None:
        tot_dur = auth_dur + meth_dur + rev_dur
        
    return {
        'duration_seconds': {
            'author': auth_dur,
            'method': meth_dur,
            'review': rev_dur,
            'total': tot_dur
        },
        'usage': {
            'author': extract_usage(author),
            'method': extract_usage(method) if method else (None if arm in ('N', 'S') else extract_usage(None)),
            'review': extract_usage(review)
        },
        'status': {
            'author': {'exit_code': author.get('exit_code'), 'timed_out': author.get('timed_out'), 'errors': len(author.get('errors', []))} if author else None,
            'method': {'exit_code': method.get('exit_code'), 'timed_out': method.get('timed_out'), 'errors': len(method.get('errors', []))} if method else None,
            'review': {'exit_code': review.get('exit_code'), 'timed_out': review.get('timed_out'), 'errors': len(review.get('errors', []))} if review else None
        },
        'cost': None
    }

def load_receipt(stage_dir, name, embedded):
    p = stage_dir / f"{name}.receipt.json"
    if not p.exists():
        suffix=" but present in complete.json" if embedded is not None else ""
        raise RuntimeError(f"Missing {name}.receipt.json"+suffix)
    if embedded is None:
        raise RuntimeError(f"Missing embedded {name} receipt in complete.json")
    data = json.loads(p.read_text())
    if embedded is not None and data != embedded:
        raise RuntimeError(f"Mismatch in {name}.receipt.json")
    return data

def load_model_receipt(stage_dir,name,embedded):
    data=load_receipt(stage_dir,name,embedded)
    if (data.get('errors') or data.get('infrastructure_failure') or
        (not data.get('timed_out') and data.get('exit_code')!=0)):
        raise RuntimeError(f'Model infrastructure failure: {name} at {stage_dir}; quality unknown, comparison not exported')
    return data

def analyze(base: Path) -> dict:
    runs_dir = base / 'runs'
    if not (runs_dir / 'complete.json').exists():
        raise RuntimeError("Missing runs/complete.json")
    manifest_path = base / 'frozen' / 'manifest.json'
    if not manifest_path.exists():
        raise RuntimeError("Missing manifest.json")
    manifest = json.loads(manifest_path.read_text())
    
    schedule = manifest['schedule']
    if len(schedule) != 18:
        raise RuntimeError("Expected exactly 18 entries in schedule")
    unique_ids = set(r['id'] for r in schedule)
    if len(unique_ids) != 18:
        raise RuntimeError("Expected exactly 18 unique IDs in schedule")
        
    from collections import Counter
    arm_counts = Counter(r['arm'] for r in schedule)
    if arm_counts != {'N': 6, 'S': 6, 'T': 6}:
        raise RuntimeError("Expected exactly 6 entries for each arm")
        
    factors=Counter((row['variant'],row['repeat'],row['arm']) for row in schedule)
    expected=Counter(itertools.product(['V1','V2','V3'],[1,2],['N','S','T']))
    if factors!=expected: raise RuntimeError('Invalid schedule factor matrix: expected six distinct NST blocks')
    if any(Path(row['id']).name!=row['id'] or row['id'] in ('','.','..') for row in schedule):
        raise RuntimeError('Invalid schedule run ID')
    var_reps = {}
    for r in schedule:
        k = (r['variant'], r['repeat'])
        var_reps.setdefault(k, []).append(r['arm'])
    for k, arms in var_reps.items():
        if set(arms) != {'N', 'S', 'T'}:
            raise RuntimeError(f"Variant/repeat {k} does not contain exactly N,S,T")
        
    results = {}
    for row in schedule:
        run_id = row['id']
        arm = row['arm']
        run_dir = runs_dir / run_id
        results[run_id] = {'arm': arm, 'variant': row['variant'], 'repeat': row['repeat'], 'stages': {}}
        for stage in [1, 2]:
            stage_dir = run_dir / f'stage{stage}'
            complete_path = stage_dir / 'complete.json'
            eval_path = stage_dir / 'evaluation.json'
            if not complete_path.exists() or not eval_path.exists():
                raise RuntimeError(f"Missing results for {run_id} stage {stage}")
                
            stage_data = json.loads(complete_path.read_text())
            eval_data = json.loads(eval_path.read_text())
            
            # Receipts validation
            load_model_receipt(stage_dir, 'author', stage_data.get('author'))
            load_model_receipt(stage_dir, 'review', stage_data.get('review'))
            if arm == 'T':
                load_model_receipt(stage_dir, 'method', stage_data.get('method'))
            load_receipt(stage_dir, 'artifact', stage_data.get('artifact'))
            
            eval_receipt_path = stage_dir / 'evaluation.receipt.json'
            if not eval_receipt_path.exists(): raise RuntimeError("Missing evaluation.receipt.json")
            eval_receipt = json.loads(eval_receipt_path.read_text())
            if eval_receipt.get('exit_code') != 0 or eval_receipt.get('timed_out') or eval_receipt.get('infrastructure_failure'):
                raise RuntimeError("Evaluation infrastructure failed")
                
            iso = eval_data.get('isolation', {})
            if iso.get('candidate_uid') != 1000 or iso.get('development_only') is not False:
                raise RuntimeError("Invalid evaluation isolation")
                
            details = eval_data.get('details', [])
            names = [d['name'] for d in details]
            if len(names) != len(set(names)): raise RuntimeError("Duplicate detail names")
            if eval_data.get('checks_total') != len(details): raise RuntimeError("checks_total mismatch")
            passed_count = sum(1 for d in details if d.get('passed'))
            if eval_data.get('checks_passed') != passed_count: raise RuntimeError("checks_passed mismatch")
            
            score=eval_data.get('score')
            if type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=1:
                raise RuntimeError('score must be finite and between zero and one')
            if any(type(detail.get('passed')) is not bool for detail in details):
                raise RuntimeError('detail passed fields must be boolean')
            expected_score = passed_count / len(details) if len(details) else 0
            if abs(eval_data.get('score', -1) - expected_score) > 1e-6: raise RuntimeError("score incongruent")
            
            common_names = {'roundtrip_create', 'source_intact', 'roundtrip_verify', 'roundtrip_match',
                'roundtrip_list', 'list_empty', 'version_snapshots', 'duplicate_id_mutation',
                'invalid_ids', 'nonexistent_id', 'overlap_rejected', 'symlink_source',
                'symlink_dest', 'symlink_repo', 'special_files', 'snapshot_corruption',
                'sigkill_interrupt_intact', 'sigkill_recovery', 'symlink_snapshot', 'dest_protected'}
                
            stage_names = set(names)
            if stage == 1:
                if stage_names != common_names: raise RuntimeError("Stage 1 missing common names or has extra")
            else:
                if stage_names != common_names.union({'max_bytes_high', 'max_bytes_low'}):
                    raise RuntimeError("Stage 2 names mismatch")
            
            artifact = stage_data.get('artifact', {}).get('files', {})
            candidate_hash = artifact.get('solution/backup.py')
            if stage == 2 and candidate_hash:
                backup_py = stage_dir / 'artifact' / 'solution' / 'backup.py'
                if not backup_py.is_file() or backup_py.is_symlink():
                    raise RuntimeError("Backup.py is missing or a symlink, but hash was provided")
                h = hashlib.sha256(backup_py.read_bytes()).hexdigest()
                if h != candidate_hash:
                    raise RuntimeError("Backup.py hash mismatch")
            
            res = summarize_resources(stage_data, arm)
            
            common_passed = 0
            common_total = 0
            max_bytes_high_passed = None
            max_bytes_low_passed = None
            
            for check in eval_data['details']:
                name = check['name']
                if name in ('max_bytes_high', 'max_bytes_low'):
                    if name == 'max_bytes_high': max_bytes_high_passed = check['passed']
                    if name == 'max_bytes_low': max_bytes_low_passed = check['passed']
                else:
                    common_total += 1
                    if check['passed']: common_passed += 1
            
            results[run_id]['stages'][stage] = {
                'evaluation': eval_data,
                'resources': res,
                'candidate_hash': candidate_hash,
                'common_passed': common_passed,
                'common_total': common_total,
                'max_bytes_high': max_bytes_high_passed,
                'max_bytes_low': max_bytes_low_passed
            }
            
    groups = {arm: {1: [], 2: []} for arm in 'NST'}
    for run_id, run_data in results.items():
        arm = run_data['arm']
        for s in [1, 2]:
            groups[arm][s].append(run_data['stages'][s])
            
    summary = {}
    for arm in 'NST':
        summary[arm] = {}
        for s in [1, 2]:
            stage_list = groups[arm][s]
            scores = [r['evaluation']['score'] for r in stage_list]
            crits = sum(1 for r in stage_list if r['evaluation']['critical_failures'])
            inconcs = sum(1 for r in stage_list if r['evaluation']['inconclusive'])
            summary[arm][s] = {
                'score_mean': mean(scores),
                'score_median': median(scores),
                'score_min': min(scores) if scores else 0,
                'score_max': max(scores) if scores else 0,
                'critical_runs': crits,
                'inconclusive_runs': inconcs,
                'count': len(stage_list)
            }
            
    pairs = {}
    for row in schedule:
        key = f"{row['variant']}-r{row['repeat']}"
        if key not in pairs:
            pairs[key] = {}
        pairs[key][row['arm']] = results[row['id']]

    differences = {'T-N': {1: {}, 2: {}}, 'T-S': {1: {}, 2: {}}}
    for s in [1, 2]:
        for comp in ['T-N', 'T-S']:
            arm1, arm2 = comp.split('-')
            diffs = []
            pair_list = []
            for key, pair in pairs.items():
                if arm1 in pair and arm2 in pair:
                    d = pair[arm1]['stages'][s]['evaluation']['score'] - pair[arm2]['stages'][s]['evaluation']['score']
                    diffs.append(d)
                    pair_list.append({'pair': key, 'delta': d})
            differences[comp][s] = {
                'mean': mean(diffs),
                'median': median(diffs),
                'range': rng(diffs),
                'pairs': pair_list
            }
            
    adaptation = {arm: [] for arm in 'NST'}
    for run_id, run_data in results.items():
        arm = run_data['arm']
        s1 = run_data['stages'][1]
        s2 = run_data['stages'][2]
        delta_common = (s2['common_passed'] / s2['common_total']) - (s1['common_passed'] / s1['common_total'])
        adaptation[arm].append({
            'run_id': run_id,
            'delta_common_passed': s2['common_passed'] - s1['common_passed'],
            'delta_common_score': delta_common,
            'max_bytes_high': s2['max_bytes_high'],
            'max_bytes_low': s2['max_bytes_low']
        })
        
    # Recolectar estadísticas de recursos (mediana/rango por autor+method y total)
    resource_stats = {arm: {} for arm in 'NST'}
    for arm in 'NST':
        all_am = []
        all_tot = []
        usages = {'input_tokens': {'complete': 0, 'missing': 0},
                  'output_tokens': {'complete': 0, 'missing': 0},
                  'cached_input_tokens': {'complete': 0, 'missing': 0}}
        for run_id, run_data in results.items():
            if run_data['arm'] != arm: continue
            for s in [1, 2]:
                res = run_data['stages'][s]['resources']
                a_dur = res['duration_seconds']['author']
                m_dur = res['duration_seconds']['method']
                t_dur = res['duration_seconds']['total']
                if a_dur is not None and m_dur is not None:
                    all_am.append(a_dur + m_dur)
                if t_dur is not None:
                    all_tot.append(t_dur)
                    
                for actor in ['author', 'method', 'review']:
                    if actor == 'method' and arm in ('N', 'S'): continue
                    actor_u = res['usage'].get(actor, {})
                    for field in usages:
                        val = actor_u.get(field) if actor_u else None
                        if val is not None:
                            usages[field]['complete'] += 1
                        else:
                            usages[field]['missing'] += 1
                            
        resource_stats[arm] = {
            'author_method_duration': {'median': median(all_am), 'range': rng(all_am)},
            'total_duration': {'median': median(all_tot), 'range': rng(all_tot)},
            'usage_availability': usages
        }

    # These descriptive summaries keep stage and role visible: six runs per cell.
    resource_by_stage={arm:{} for arm in 'NST'}
    for arm in 'NST':
        for stage in [1,2]:
            records=groups[arm][stage]
            totals=[record['resources']['duration_seconds']['total'] for record in records]
            role_summary={}
            for role in ['author','method','review']:
                if role=='method' and arm!='T':
                    role_summary[role]={'executed':False}; continue
                durations=[record['resources']['duration_seconds'][role] for record in records]
                valid=[value for value in durations if value is not None]
                fields={}
                for field in ['input_tokens','output_tokens','cached_input_tokens']:
                    values=[record['resources']['usage'][role][field] for record in records]
                    known=[value for value in values if value is not None]
                    fields[field]={'median':median(known),'range':rng(known),
                                   'known_sum':sum(known) if known else None,
                                   'missing':len(values)-len(known),'reported':len(known)}
                role_summary[role]={'executed':True,'seconds':{'median':median(valid),
                                      'range':rng(valid),'missing':len(durations)-len(valid)},
                                    'tokens':fields}
            known_totals=[value for value in totals if value is not None]
            resource_by_stage[arm][stage]={'n_runs':len(records),'roles':role_summary,
                'total_seconds':{'median':median(known_totals),'range':rng(known_totals),
                                 'missing':len(totals)-len(known_totals)}}

    candidates = []
    for position, row in enumerate(schedule):
        run_id = row['id']
        s2 = results[run_id]['stages'][2]
        ev = s2['evaluation']
        if ev['score'] == 1.0 and not ev['critical_failures'] and not ev['inconclusive'] and s2['candidate_hash']:
            res = s2['resources']
            a_dur = res['duration_seconds']['author']
            m_dur = res['duration_seconds']['method']
            time_spent = (a_dur + m_dur) if (a_dur is not None and m_dur is not None) else float('inf')
            candidates.append((time_spent, position, run_id))
            
    if candidates:
        candidates.sort()
        best = candidates[0][2]
    else:
        best = None
        
    return {
        'summary': summary,
        'differences': differences,
        'adaptation': adaptation,
        'selection': best,
        'resource_stats': resource_stats,
        'resource_by_stage': resource_by_stage,
        'runs': results
    }

def generate_report(analysis_data, schedule):
    lines = ["# Reporte del Piloto\n"]
    lines.append("## Limitaciones")
    lines.append("- n=6 por brazo")
    lines.append("- un modelo configurado, no snapshot verificado")
    lines.append("- cegamiento imperfecto")
    lines.append("- cuotas compartidas")
    lines.append("- muestras del mismo dominio")
    lines.append("- revisión local declarada")
    lines.append("- sin eficacia de campo demostrada\n")
    
    lines.append("## Selección de Producto")
    if analysis_data['selection']:
        lines.append(f"Producto seleccionado: **{analysis_data['selection']}**")
    else:
        lines.append("Reparación fuera de comparación, no elegir referencia de desarrollo como corrida.\n")
        
    lines.append("## Resumen por Brazo y Etapa")
    lines.append("| Brazo | Etapa | Score Medio | Score Mediana | Rango | Críticos | Inconclusos |")
    lines.append("|---|---|---|---|---|---|---|")
    for arm in 'NST':
        for s in [1, 2]:
            st = analysis_data['summary'][arm][s]
            lines.append(f"| {arm} | {s} | {st['score_mean']:.3f} | {st['score_median']:.3f} | [{st['score_min']:.3f}, {st['score_max']:.3f}] | {st['critical_runs']} | {st['inconclusive_runs']} |")
            
    lines.append("\n## Diferencias Pareadas")
    lines.append("| Comparación | Etapa | Score Delta Medio | Mediana | Rango |")
    lines.append("|---|---|---|---|---|")
    for s in [1, 2]:
        for comp in ['T-N', 'T-S']:
            st = analysis_data['differences'][comp][s]
            r_min, r_max = st['range']
            lines.append(f"| {comp} | {s} | {st['mean']:.3f} | {st['median']:.3f} | [{r_min:.3f}, {r_max:.3f}] |")
            
    lines.append("\n## Adaptación (Cambio en Checks Comunes y Nuevos)")
    lines.append("| Run | Delta Comunes (Puntos) | Delta Comunes (Score) | max_bytes_high | max_bytes_low |")
    lines.append("|---|---|---|---|---|")
    for arm in 'NST':
        for ad in analysis_data['adaptation'][arm]:
            lines.append(f"| {ad['run_id']} | {ad['delta_common_passed']} | {ad['delta_common_score']:.3f} | {ad['max_bytes_high']} | {ad['max_bytes_low']} |")
            
    lines.append("\n## Resultados Detallados (18x2)")
    lines.append("| ID | Arm | Var | Rep | Etapa | Score | Checks | Críticos | Inconclusos | Tiempo (A+M) | Hash Candidato | Coste |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for row in schedule:
        run_id = row['id']
        run_data = analysis_data['runs'][run_id]
        for s in [1, 2]:
            s_data = run_data['stages'][s]
            ev = s_data['evaluation']
            res = s_data['resources']
            a_dur = res['duration_seconds']['author']
            m_dur = res['duration_seconds']['method']
            t_str = f"{(a_dur + m_dur):.1f}s" if (a_dur is not None and m_dur is not None) else "Desconocido"
            crit = len(ev['critical_failures'])
            inc = "Sí" if ev['inconclusive'] else "No"
            h = s_data['candidate_hash'][:8] if s_data['candidate_hash'] else "N/A"
            cost = res['cost'] if res['cost'] is not None else "null"
            lines.append(f"| {run_id} | {row['arm']} | {row['variant']} | {row['repeat']} | {s} | {ev['score']:.3f} | {ev['checks_passed']}/{ev['checks_total']} | {crit} | {inc} | {t_str} | {h} | {cost} |")
            
    lines.append("\n## Recursos por etapa y rol")
    lines.append("Cada celda resume seis corridas; cache es parte de input y no se suma otra vez. Desconocido no significa cero.")
    lines.append("\n| Brazo | Etapa | Rol | Tiempo mediano (s) | Input mediano | Output mediano | Cache mediana | Usos input ausentes |")
    lines.append("|---|---|---|---|---|---|---|---|")
    def show(value): return 'desconocido' if value is None else f'{value:.1f}'
    for arm in 'NST':
        for stage in [1,2]:
            for role,data in analysis_data['resource_by_stage'][arm][stage]['roles'].items():
                if not data['executed']: continue
                tokens=data['tokens']
                lines.append(f"| {arm} | {stage} | {role} | {show(data['seconds']['median'])} | {show(tokens['input_tokens']['median'])} | {show(tokens['output_tokens']['median'])} | {show(tokens['cached_input_tokens']['median'])} | {tokens['input_tokens']['missing']}/6 |")
    lines.append("\n## Fallos críticos conservados")
    for row in schedule:
        for stage in [1,2]:
            failures=analysis_data['runs'][row['id']]['stages'][stage]['evaluation']['critical_failures']
            if failures: lines.append(f"- {row['id']} etapa {stage}: {', '.join(failures)}")
    lines.append("\nLa selección es una sugerencia técnica sujeta a comprobar el producto en un runtime limpio y publicar su procedencia. Las diferencias de piloto no prueban eficacia general ni de campo. Costes monetarios desconocidos.")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--output', type=Path, default=Path('analysis'))
    args = parser.parse_args()
    
    try:
        data = analyze(args.base)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
        
    out_dir = args.output
    if not out_dir.is_absolute():
        out_dir = args.base / args.output
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_dir / 'results.json', 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    manifest_path = args.base / 'frozen' / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    report = generate_report(data, manifest['schedule'])
    
    with open(out_dir / 'report.md', 'w') as f:
        f.write(report)

if __name__ == '__main__':
    main()
