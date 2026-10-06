"""Prospective v3 finite recipe candidates, never supplied to delivery authors.

These are trusted evaluator oracles, not delivered programmes or model outputs.
Fraction integer oracles use decimal strings internally to avoid changing the
host's decimal-conversion policy; subject output must still contain JSON ints.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import json

TASK_FILES = {'fractionmix': 'fractionmix.py', 'policypick': 'policypick.py', 'listpatch': 'listpatch.py'}
TASK_COUNTS = {'fractionmix': 84, 'policypick': 82, 'listpatch': 84}
ERROR = b'{"error":"invalid_input"}\n'
STREAM_LIMIT = 2097152


def wire(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()


def decimal_text(value):
    """Exact conversion in bounded decimal chunks, without global sys settings."""
    sign = '-' if value < 0 else ''
    value = abs(value)
    chunks = []
    while value:
        value, chunk = divmod(value, 10**9)
        chunks.append(chunk)
    return sign + (str(chunks[-1]) + ''.join(f'{v:09d}' for v in reversed(chunks[:-1])) if chunks else '0')


def fraction_expected(terms):
    total = sum((Fraction(n, d) for n, d in terms), Fraction())
    return {'numerator_decimal': decimal_text(total.numerator),
            'denominator_decimal': decimal_text(total.denominator), 'term_count': len(terms)}


def coprime_denominators():
    primes = []
    candidate = 2
    while len(primes) < 1000:
        if all(candidate % p for p in primes if p * p <= candidate):
            primes.append(candidate)
        candidate += 1
    values = []
    for p in primes:
        power = p
        while power * p <= 10**9:
            power *= p
        values.append(power)
    return values


class Builder:
    def __init__(self, task):
        self.task = task
        self.rows = []

    def add(self, group, name, raw, expected=None, *, public=False, argv=(), held=False, relation=None):
        if not isinstance(raw, bytes):
            raw = wire(raw)
        self.rows.append({'id': f'{self.task}-{group}-{name}', 'task': self.task,
                          'group': group, 'stdin_hex': raw.hex(), 'argv': list(argv),
                          'stdin_mode': 'held_open' if held else 'closed',
                          'expected': expected, 'public': public, 'relation': relation})

    def framing(self, valid, expected, nested_duplicate, nonfinite):
        raw = wire(valid)
        for name, bad in [('empty', b''), ('whitespace-only', b' \t\r\n'),
                          ('bad-utf8', b'\xff' + raw), ('BOM', b'\xef\xbb\xbf' + raw),
                          ('raw-NUL', raw + b'\x00'), ('concatenated', raw + raw),
                          ('truncated', raw[:-1]), ('nested-duplicate', nested_duplicate),
                          ('NaN', nonfinite.replace(b'NUMBER', b'NaN')),
                          ('Infinity', nonfinite.replace(b'NUMBER', b'Infinity')),
                          ('negative-Infinity', nonfinite.replace(b'NUMBER', b'-Infinity'))]:
            self.add('format', name, bad)
        first = next(iter(valid))
        escaped = '\\u%04x' % ord(first[0]) + first[1:]
        rest = wire({k: v for k, v in valid.items() if k != first})[1:-1]
        duplicate = b'{"' + first.encode() + b'":' + wire(valid[first]) + b',"' + escaped.encode() + b'":' + wire(valid[first])
        if rest:
            duplicate += b',' + rest
        self.add('format', 'top-escaped-duplicate', duplicate + b'}')
        self.add('format', 'outer-whitespace-valid', b' \t\r\n' + raw + b' \r\n', expected)
        self.add('boundaries', '65536-bytes', raw + b' ' * (65536 - len(raw)), expected)
        self.add('boundaries', '65537-bytes', raw + b' ' * (65537 - len(raw)))
        self.add('argv', 'help-with-data', raw, argv=('--help',))
        self.add('argv', 'positional-with-data', raw, argv=('anything',))
        self.add('argv', 'before-stdin', b'', argv=('--help',), held=True)

    def finish(self):
        count = TASK_COUNTS[self.task]
        if len(self.rows) != count or len({r['id'] for r in self.rows}) != count:
            raise ValueError(f'candidate {self.task} recipe count/identity mismatch: {len(self.rows)}')
        if sum(r['public'] for r in self.rows) != 2:
            raise ValueError('exactly two public examples per task required')
        return self.rows


def fractionmix_recipes():
    b = Builder('fractionmix')
    def good(name, pairs, *, public=False, relation=None):
        b.add('arithmetic', name, {'terms': [{'numerator': n, 'denominator': d} for n, d in pairs]},
              fraction_expected(pairs), public=public, relation=relation)
    good('public-sum', [(1, 2), (1, 3)], public=True)
    good('public-cancel', [(2, 4), (-1, 2)], public=True)
    for name, pairs in [('empty', []), ('zero', [(0, 7)]), ('reduce', [(12, 18)]),
                        ('negative-reduce', [(-12, 18)]), ('integer', [(7, 1)]),
                        ('duplicates-count', [(1, 3)] * 3), ('all-cancel', [(1, 3), (1, 3), (-2, 3)]),
                        ('mixed-signs', [(5, 6), (-7, 10), (11, 15)]),
                        ('large-positive-result', [(10**9, 1), (10**9, 1)]),
                        ('large-negative-result', [(-10**9, 1), (-10**9, 1)]),
                        ('inclusive-numerators', [(-10**9, 1), (10**9, 1)]),
                        ('max-denominator', [(1, 10**9)]), ('zero-max-denominator', [(0, 10**9)]),
                        ('1000-zero-terms', [(0, 1)] * 1000), ('1000-one-terms', [(1, 1)] * 1000),
                        ('exact-beyond-float', [(1, 536870912), (1, 387420489)]),
                        ('different-denominator-duplicates', [(1, 2), (2, 4), (-3, 6)]),
                        ('one-third-ten-times', [(1, 3)] * 10),
                        ('unit-negative', [(-1, 1)]), ('non-reduced-zero', [(0, 100)])]:
        good(name, pairs)
    pairs = [(3, 5), (-2, 7), (1, 11)]
    good('order-base', pairs)
    good('order-reversed', list(reversed(pairs)), relation={'same_output_as': 'fractionmix-arithmetic-order-base'})
    good('7331-digit-denominator', [(1, d) for d in coprime_denominators()])
    valid = {'terms': [{'numerator': 1, 'denominator': 2}]}
    expected = fraction_expected([(1, 2)])
    for name, value in [('root-list', []), ('root-null', None), ('missing-terms', {}),
                        ('extra-top', {**valid, 'other': 1}), ('terms-null', {'terms': None}),
                        ('terms-object', {'terms': {}}), ('term-null', {'terms': [None]}),
                        ('term-list', {'terms': [[]]}), ('missing-numerator', {'terms': [{'denominator': 2}]}),
                        ('missing-denominator', {'terms': [{'numerator': 1}]}),
                        ('extra-term', {'terms': [{'numerator': 1, 'denominator': 2, 'x': 0}]})]:
        b.add('schema', name, value)
    for field in ('numerator', 'denominator'):
        for label, value in [('bool', True), ('float', 1.0), ('string', '1'), ('null', None), ('array', []), ('object', {})]:
            term = dict(valid['terms'][0]); term[field] = value
            b.add('types', field + '-' + label, {'terms': [term]})
    for name, n, d in [('numerator-low', -10**9 - 1, 1), ('numerator-high', 10**9 + 1, 1),
                       ('denominator-high', 1, 10**9 + 1), ('denominator-zero', 1, 0),
                       ('denominator-negative', 1, -1), ('zero-does-not-skip-invalid', 0, 0)]:
        b.add('boundaries', name, {'terms': [{'numerator': n, 'denominator': d}]})
    b.add('boundaries', '1001-terms', {'terms': valid['terms'] * 1001})
    b.add('boundaries', 'invalid-even-after-cancellation', {'terms': [*valid['terms'], {'numerator': -1, 'denominator': 2}, {'numerator': 0, 'denominator': 0}]})
    b.add('arithmetic', 'negative-zero-numerator', b'{"terms":[{"numerator":-0,"denominator":2}]}', fraction_expected([(0, 2)]))
    b.add('boundaries', 'negative-zero-denominator', b'{"terms":[{"numerator":1,"denominator":-0}]}')
    b.framing(valid, expected, b'{"terms":[{"numerator":1,"\\u006eumerator":1,"denominator":2}]}',
              b'{"terms":[{"numerator":NUMBER,"denominator":2}]}')
    # Nonfinite denominator and integer exponent syntax are separately visible.
    for name, raw in [('denominator-NaN', b'{"terms":[{"numerator":1,"denominator":NaN}]}'),
                      ('denominator-Infinity', b'{"terms":[{"numerator":1,"denominator":Infinity}]}'),
                      ('denominator-negative-Infinity', b'{"terms":[{"numerator":1,"denominator":-Infinity}]}'),
                      ('exponent-numerator', b'{"terms":[{"numerator":1e0,"denominator":2}]}'),
                      ('exponent-denominator', b'{"terms":[{"numerator":1,"denominator":2e0}]}'),
                      ('root-boolean', b'true'), ('trailing-comma', b'{"terms":[],}'),
                      ('escaped-key-valid', b'{"\\u0074erms":[{"numerator":1,"denominator":2}]}')]:
        b.add('format', name, raw, expected if name == 'escaped-key-valid' else None)
    return b.finish()


def rule(name='r', priority=0, requires=()):
    return {'name': name, 'priority': priority, 'requires': list(requires)}


def query(identity='q', tags=()):
    return {'id': identity, 'tags': list(tags)}


def decisions(*rows):
    return {'decisions': [{'id': identity, 'rule': name} for identity, name in rows]}


def policypick_recipes():
    b = Builder('policypick')
    def good(name, rules, queries, value, public=False, relation=None):
        b.add('semantics', name, {'rules': rules, 'queries': queries}, value, public=public, relation=relation)
    good('public-priority', [rule('default'), rule('staff', 2, ['internal'])],
         [query('q1', ['internal', 'internal']), query('q2')], decisions(('q1', 'staff'), ('q2', 'default')), True)
    good('public-tie', [rule('z', 3, ['x']), rule('A', 3, ['x'])],
         [query('yes', ['x']), query('no')], decisions(('yes', 'A'), ('no', None)), True)
    good('empty-both', [], [], decisions())
    good('no-rules', [], [query()], decisions(('q', None)))
    good('no-queries', [rule()], [], decisions())
    good('requires-and-tags-duplicates', [rule('r', 1, ['x', 'x'])], [query('q', ['x', 'x'])], decisions(('q', 'r')))
    good('priority-over-name', [rule('a', 1), rule('z', 2)], [query()], decisions(('q', 'z')))
    good('negative-priority', [rule('a', -2), rule('z', -1)], [query()], decisions(('q', 'z')))
    good('literal-spaces-tabs', [rule('space', 1, [' x ']), rule('tab', 1, ['\t'])],
         [query('a', ['x']), query('b', [' x ']), query('c', ['\t'])], decisions(('a', None), ('b', 'space'), ('c', 'tab')))
    good('unicode-codepoints', [rule('Å'), rule('A\u030a')], [query()], decisions(('q', 'A\u030a')))
    good('no-unicode-normalization', [rule('r', 1, ['é'])], [query('q', ['e\u0301'])], decisions(('q', None)))
    good('namespaces-independent', [rule('same')], [query('same')], decisions(('same', 'same')))
    good('query-order', [rule()], [query('z'), query('a')], decisions(('z', 'r'), ('a', 'r')))
    good('order-base', [rule('z'), rule('a')], [query()], decisions(('q', 'a')))
    good('order-reversed', [rule('a'), rule('z')], [query()], decisions(('q', 'a')), relation={'same_output_as': 'policypick-semantics-order-base'})
    valid = {'rules': [rule()], 'queries': [query()]}
    for name, value in [('root-list', []), ('root-null', None), ('missing-queries', {'rules': []}),
                        ('missing-rules', {'queries': []}), ('extra-top', {**valid, 'x': 1}),
                        ('rules-null', {**valid, 'rules': None}), ('queries-null', {**valid, 'queries': None}),
                        ('rule-null', {**valid, 'rules': [None]}), ('query-null', {**valid, 'queries': [None]}),
                        ('rule-extra', {**valid, 'rules': [{**rule(), 'x': 1}]}),
                        ('query-extra', {**valid, 'queries': [{**query(), 'x': 1}]}),
                        ('missing-requires', {**valid, 'rules': [{'name': 'r', 'priority': 0}]}),
                        ('missing-tags', {**valid, 'queries': [{'id': 'q'}]})]:
        b.add('schema', name, value)
    for label, value in [('bool', True), ('float', 0.0), ('string', '0')]:
        b.add('types', 'priority-' + label, {**valid, 'rules': [rule(priority=value)]})
    b.add('types', 'requires-string', {**valid, 'rules': [{**rule(), 'requires': 'x'}]})
    b.add('types', 'tags-string', {**valid, 'queries': [{**query(), 'tags': 'x'}]})
    b.add('identity', 'duplicate-rule', {**valid, 'rules': [rule(), rule()]})
    b.add('identity', 'duplicate-query', {**valid, 'queries': [query(), query()]})
    for label, value in [('low', -10**9 - 1), ('high', 10**9 + 1)]:
        b.add('boundaries', 'priority-' + label, {**valid, 'rules': [rule(priority=value)]})
    good('priority-inclusive', [rule('a', -10**9), rule('z', 10**9)], [query()], decisions(('q', 'z')))
    good('all-strings-64-bytes', [rule('r' * 64, 0, ['t' * 64])], [query('q' * 64, ['t' * 64])], decisions(('q' * 64, 'r' * 64)))
    for field in ('name', 'id', 'requires', 'tags'):
        for label, text in [('empty', ''), ('65-bytes', 'x' * 65)]:
            value = copy.deepcopy(valid)
            if field in ('name', 'requires'):
                value['rules'][0][field] = [text] if field == 'requires' else text
            else:
                value['queries'][0][field] = [text] if field == 'tags' else text
            b.add('strings', field + '-' + label, value)
    good('unicode-64-bytes', [rule('é' * 32)], [query()], decisions(('q', 'é' * 32)))
    b.add('strings', 'unicode-66-bytes', {**valid, 'rules': [rule('é' * 33)]})
    for field, text in [('name', '\x00'), ('id', '\r'), ('requires', '\n'), ('tags', '\ud800')]:
        value = copy.deepcopy(valid)
        target = value['rules'][0] if field in ('name', 'requires') else value['queries'][0]
        target[field] = [text] if field in ('requires', 'tags') else text
        b.add('strings', field + '-forbidden', value)
    good('1000-tags-and-requires', [rule('r', 0, ['x'] * 1000)], [query('q', ['x'] * 1000)], decisions(('q', 'r')))
    b.add('boundaries', '1001-requires', {**valid, 'rules': [rule(requires=['x'] * 1001)]})
    b.add('boundaries', '1001-tags', {**valid, 'queries': [query(tags=['x'] * 1001)]})
    good('1000-rules', [rule(f'r{i:04}') for i in range(1000)], [query()], decisions(('q', 'r0000')))
    b.add('boundaries', '1001-rules', {**valid, 'rules': [rule(f'r{i:04}') for i in range(1001)]})
    good('1000-queries', [], [query(f'q{i:04}') for i in range(1000)], decisions(*[(f'q{i:04}', None) for i in range(1000)]))
    b.add('boundaries', '1001-queries', {'rules': [], 'queries': [query(f'q{i:04}') for i in range(1001)]})
    b.framing(valid, decisions(('q', 'r')), b'{"rules":[{"name":"r","\\u006eame":"r","priority":0,"requires":[]}],"queries":[]}',
              b'{"rules":[{"name":"r","priority":NUMBER,"requires":[]}],"queries":[]}')
    b.add('types', 'unused-invalid-rule-with-empty-queries', {'rules': [rule(priority=True)], 'queries': []})
    b.add('types', 'nonwinning-invalid-rule', {'rules': [rule('a', 1), rule('b', False)], 'queries': [query()]})
    b.add('strings', 'requires-nonstring-element', {**valid, 'rules': [rule(requires=[1])]})
    b.add('strings', 'tags-nonstring-element', {**valid, 'queries': [query(tags=[1])]})
    return b.finish()


def operation(op='insert', index=0, value=1):
    return {'op': op, 'index': index, **({'value': value} if op != 'delete' else {})}


def patched(items, applied):
    return {'items': items, 'applied': applied}


def listpatch_recipes():
    b = Builder('listpatch')
    def good(name, items, operations, result, public=False):
        b.add('semantics', name, {'items': items, 'operations': operations}, patched(result, len(operations)), public=public)
    good('public-sequence', [10, 20], [operation(index=1, value=15), operation('replace', 0, 9), operation('delete', 2)], [9, 15], True)
    good('public-return-empty', [], [operation(value=-2), operation('delete')], [], True)
    for name, items, ops, result in [('empty', [], [], []), ('unchanged', [1, -2, 3], [], [1, -2, 3]),
                                   ('insert-first', [1, 2], [operation(value=7)], [7, 1, 2]),
                                   ('insert-last', [1, 2], [operation(index=2, value=7)], [1, 2, 7]),
                                   ('replace-first', [1, 2], [operation('replace', 0, 7)], [7, 2]),
                                   ('replace-last', [1, 2], [operation('replace', 1, 7)], [1, 7]),
                                   ('delete-first', [1, 2], [operation('delete', 0)], [2]),
                                   ('delete-last', [1, 2], [operation('delete', 1)], [1]),
                                   ('insert-current-index', [1], [operation(index=1, value=2), operation('replace', 1, 3)], [1, 3]),
                                   ('delete-current-index', [1, 2, 3], [operation('delete', 0), operation('delete', 1)], [2]),
                                   ('duplicates-count', [], [operation(), operation()], [1, 1]),
                                   ('replace-counts', [1], [operation('replace', 0, 1)] * 3, [1]),
                                   ('inclusive-values', [-10**9, 10**9], [operation('replace', 0, 10**9)], [10**9, 10**9]),
                                   ('1000-items-delete', list(range(1000)), [operation('delete', 999)], list(range(999))),
                                   ('1000-operations', [], [operation(), operation('delete')] * 500, []),
                                   ('grow-to1000', list(range(999)), [operation(index=999, value=-1)], [*range(999), -1]),
                                   ('replace-index999', list(range(1000)), [operation('replace', 999, -1)], [*range(999), -1])]:
        good(name, items, ops, result)
    valid = {'items': [1], 'operations': [operation('replace', 0, 2)]}
    for name, value in [('root-list', []), ('root-null', None), ('missing-items', {'operations': []}),
                        ('missing-operations', {'items': []}), ('extra-top', {**valid, 'x': 1}),
                        ('items-null', {**valid, 'items': None}), ('operations-null', {**valid, 'operations': None}),
                        ('operation-null', {**valid, 'operations': [None]}),
                        ('missing-op', {**valid, 'operations': [{'index': 0, 'value': 2}]}),
                        ('missing-index', {**valid, 'operations': [{'op': 'insert', 'value': 2}]}),
                        ('missing-insert-value', {**valid, 'operations': [{'op': 'insert', 'index': 0}]}),
                        ('missing-replace-value', {**valid, 'operations': [{'op': 'replace', 'index': 0}]}),
                        ('extra-delete-value', {**valid, 'operations': [{'op': 'delete', 'index': 0, 'value': 1}]}),
                        ('extra-operation', {**valid, 'operations': [{**operation(), 'x': 1}]})]:
        b.add('schema', name, value)
    for field in ('item', 'index', 'value'):
        for label, value in [('bool', True), ('float', 0.0), ('string', '0'), ('null', None)]:
            raw = copy.deepcopy(valid)
            if field == 'item': raw['items'] = [value]
            else: raw['operations'][0][field] = value
            b.add('types', field + '-' + label, raw)
    for name, value in [('remove', 'remove'), ('uppercase', 'INSERT'), ('space', 'insert '), ('not-string', 1)]:
        b.add('schema', 'op-' + name, {**valid, 'operations': [{'op': value, 'index': 0, 'value': 1}]})
    for field in ('item', 'value'):
        for label, value in [('low', -10**9 - 1), ('high', 10**9 + 1)]:
            raw = copy.deepcopy(valid)
            if field == 'item': raw['items'] = [value]
            else: raw['operations'][0]['value'] = value
            b.add('boundaries', field + '-' + label, raw)
    for name, raw in [('negative-index', {**valid, 'operations': [operation('replace', -1)]}),
                      ('1001-index', {**valid, 'operations': [operation('replace', 1001)]}),
                      ('replace-at-length', {**valid, 'operations': [operation('replace', 1)]}),
                      ('delete-at-length', {**valid, 'operations': [operation('delete', 1)]}),
                      ('insert-beyond-length', {**valid, 'operations': [operation(index=2)]}),
                      ('delete-empty', {'items': [], 'operations': [operation('delete')]}),
                      ('replace-empty', {'items': [], 'operations': [operation('replace')]}),
                      ('1001-items', {'items': [0] * 1001, 'operations': []}),
                      ('1001-operations', {'items': [0], 'operations': [operation('replace', 0, 0)] * 1001}),
                      ('transient1001-not-compensated', {'items': [0] * 1000, 'operations': [operation(), operation('delete')]}),
                      ('future-index-not-valid-now', {'items': [], 'operations': [operation('replace', 0, 7), operation()]}),
                      ('no-partial-output', {'items': [], 'operations': [operation(), operation('delete', 5)]})]:
        b.add('boundaries', name, raw)
    b.add('semantics', 'negative-zero-int', b'{"items":[-0],"operations":[{"op":"replace","index":-0,"value":-0}]}', patched([0], 1))
    b.framing(valid, patched([2], 1), b'{"items":[1],"operations":[{"op":"replace","index":0,"\\u0069ndex":0,"value":2}]}',
              b'{"items":[1],"operations":[{"op":"replace","index":0,"value":NUMBER}]}')
    return b.finish()


def recipes(task=None):
    builders = {'fractionmix': fractionmix_recipes, 'policypick': policypick_recipes, 'listpatch': listpatch_recipes}
    if task is None:
        return [r for build in builders.values() for r in build()]
    if task not in builders:
        raise ValueError('unknown prospective task')
    return builders[task]()


class JsonInteger(str):
    """Exact JSON integer lexeme, distinct from an ordinary JSON string/bool."""


def output_integer(value):
    if len(value.lstrip('-')) > 10000:
        raise ValueError('output integer beyond all contractual result bounds')
    return JsonInteger('0' if value == '-0' else value)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def reject_number(value):
    raise ValueError('noninteger/nonfinite JSON output')


def typed_equal(actual, expected):
    if type(expected) is int:
        return type(actual) is JsonInteger and actual == str(expected)
    if type(expected) is dict:
        return type(actual) is dict and set(actual) == set(expected) and all(typed_equal(actual[k], v) for k, v in expected.items())
    if type(expected) is list:
        return type(actual) is list and len(actual) == len(expected) and all(typed_equal(a, e) for a, e in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def judge(recipe, result):
    if result.get('infrastructure_error'):
        return {'status': 'inconclusive', 'reason': 'subject infrastructure failure'}
    if result.get('timed_out') or result.get('truncated_streams'):
        return {'status': 'fail', 'reason': 'subject timeout or stream limit'}
    out, err = result['stdout'], result['stderr']
    if type(out) is not bytes or type(err) is not bytes or max(len(out), len(err)) > STREAM_LIMIT:
        return {'status': 'fail', 'reason': 'invalid/oversized captured streams'}
    if recipe['expected'] is None:
        okay = result['exit_code'] == 2 and out == b'' and err == ERROR
        return {'status': 'pass' if okay else 'fail', 'reason': 'exact invalid_input response' if okay else 'invalid_input contract violated'}
    if result['exit_code'] != 0 or err or not out.startswith(b'{') or not out.endswith(b'}\n'):
        return {'status': 'fail', 'reason': 'success exit/framing/stderr contract violated'}
    try:
        value = json.loads(out[:-1].decode('utf-8', 'strict'), object_pairs_hook=unique_pairs,
                           parse_int=output_integer, parse_float=reject_number, parse_constant=reject_number)
    except (ValueError, UnicodeError, RecursionError):
        return {'status': 'fail', 'reason': 'strict output JSON violated'}
    target = recipe['expected']
    if recipe['task'] == 'fractionmix':
        okay = (type(value) is dict and set(value) == {'numerator', 'denominator', 'term_count'}
                and type(value['numerator']) is JsonInteger and value['numerator'] == target['numerator_decimal']
                and type(value['denominator']) is JsonInteger and value['denominator'] == target['denominator_decimal']
                and typed_equal(value['term_count'], target['term_count']))
    else:
        okay = typed_equal(value, target)
    return {'status': 'pass' if okay else 'fail', 'reason': 'exact typed oracle matched' if okay else 'exact typed oracle mismatch'}
