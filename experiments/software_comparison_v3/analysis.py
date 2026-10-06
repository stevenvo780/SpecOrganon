"""Prospective descriptive metrics only; no inference or receipt verification.

The controller verifies real execution/provenance before handing rows here. A
recipe is not an independent author replicate. Missing evaluation is kept unknown.
"""
from __future__ import annotations

import statistics


class AnalysisError(ValueError):
    pass


def functional_summary(matrix, rows, *, evaluated=True):
    catalog = {r['id']: r for r in matrix}
    if not matrix or len(catalog) != len(matrix):
        raise AnalysisError('unique nonempty frozen recipe population required')
    statuses = {}
    for row in rows:
        if (type(row) is not dict or row.get('id') not in catalog or row['id'] in statuses
                or row.get('status') not in ('pass', 'fail', 'inconclusive')):
            raise AnalysisError('unknown/duplicate recipe or invalid row status')
        statuses[row['id']] = row['status']
    if not evaluated and rows:
        raise AnalysisError('unevaluated prerequisite cannot carry behavioural results')
    if evaluated and set(statuses) != set(catalog):
        raise AnalysisError('evaluated closure requires every frozen recipe, including explicit infrastructure rows')

    def group(ids):
        n = len(ids)
        counts = {s: sum(statuses.get(i) == s for i in ids) for s in ('pass', 'fail', 'inconclusive')}
        missing = sum(i not in statuses for i in ids)
        uncertain = counts['inconclusive'] + missing
        return {**counts, 'not_evaluated': missing, 'denominator': n,
                'lower': counts['pass'] / n if n else None,
                'upper': (counts['pass'] + uncertain) / n if n else None}

    total = group(list(catalog))
    valid = group([i for i, r in catalog.items() if r['expected'] is not None])
    invalid = group([i for i, r in catalog.items() if r['expected'] is None])
    public = group([i for i, r in catalog.items() if r['public']])
    reserved = group([i for i, r in catalog.items() if not r['public']])
    balanced = {'lower': (valid['lower'] + invalid['lower']) / 2,
                'upper': (valid['upper'] + invalid['upper']) / 2} if valid['denominator'] and invalid['denominator'] else None
    return {'evaluated': evaluated, 'F_total': total, 'F_valid_success': valid,
            'F_invalid_rejection': invalid, 'F_public': public, 'F_reserved': reserved,
            'F_balanced_valid_invalid_secondary': balanced,
            'contract_complete': bool(evaluated and total['pass'] == total['denominator']),
            'method_superiority': 'not inferred from this metric',
            'native_replicates': 'counted by campaign cells, never by recipes'}


def descriptive_differences(pairs):
    """All fixed paired blocks as bounded intervals, without dropping unknowns."""
    intervals = []
    for identity, treatment, control in pairs:
        for score in (treatment, control):
            if (type(score) is not dict or set(score) != {'lower', 'upper'}
                    or any(type(v) not in (int, float) for v in score.values())
                    or not 0 <= score['lower'] <= score['upper'] <= 1):
                raise AnalysisError('bounded score interval required')
        intervals.append({'block_id': identity, 'lower': treatment['lower'] - control['upper'],
                          'upper': treatment['upper'] - control['lower']})
    if not intervals or len({i['block_id'] for i in intervals}) != len(intervals):
        raise AnalysisError('unique nonempty fixed paired blocks required')
    return {'blocks': intervals, 'n_blocks': len(intervals),
            'mean': {'lower': statistics.mean(r['lower'] for r in intervals),
                     'upper': statistics.mean(r['upper'] for r in intervals)},
            'median': {'lower': statistics.median(r['lower'] for r in intervals),
                       'upper': statistics.median(r['upper'] for r in intervals)},
            'range': {'lower': min(r['lower'] for r in intervals), 'upper': max(r['upper'] for r in intervals)},
            'scope': 'descriptive interval bounds, no p-value, confidence level or field causal claim'}
