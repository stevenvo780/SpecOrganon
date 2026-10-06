"""Eighty prospective LotLedger recipes; never mounted to generation roles."""
from __future__ import annotations

import json

from specorganon.ledger import strict_json_loads


GROUPS = ('legal', 'identity', 'order', 'types', 'format', 'boundaries')


def event(identity='a', op='receive', lot='L', site='A', quantity=1, **extra):
    value = {'id': identity, 'op': op, 'lot': lot, 'quantity': quantity}
    if op == 'move':
        value.update({'from': site, 'to': extra.pop('to', 'B')})
    else:
        value['site'] = site
    value.update(extra)
    return value


def lines(*events):
    return ''.join(json.dumps(e, ensure_ascii=False, separators=(',', ':')) + '\n'
                   for e in events).encode('utf-8')


def expected(unique, duplicates=0, rows=()):
    return {'unique_events': unique, 'duplicate_events': duplicates,
            'stocks': [{'lot': lot, 'site': site, 'quantity': quantity}
                       for lot, site, quantity in rows]}


def recipes():
    result = []

    def add(group, identity, raw, value=None, *, public=False, argv=(), relation=None):
        if isinstance(raw, str):
            raw = raw.encode('utf-8')
        result.append({'id': group + '-' + identity, 'group': group,
                       'stdin_hex': raw.hex(), 'argv': list(argv), 'expected': value,
                       'public': public, 'relation': relation})

    r = event('r1', quantity=7)
    c = event('c1', 'consume', quantity=2)
    m = event('m1', 'move', quantity=3)
    add('legal', 'public-empty', b'', expected(0), public=True)
    add('legal', 'public-transfer', lines(r, c, m, dict(reversed(list(c.items())))),
        expected(3, 1, [('L', 'A', 2), ('L', 'B', 3)]), public=True)
    add('legal', 'receive', lines(event()), expected(1, rows=[('L', 'A', 1)]))
    add('legal', 'accumulate', lines(event('a', quantity=2), event('b', quantity=3)),
        expected(2, rows=[('L', 'A', 5)]))
    add('legal', 'zero-omitted', lines(event('a'), event('b', 'consume')), expected(2))
    add('legal', 'move-all', lines(event('a', quantity=4), event('b', 'move', quantity=4)),
        expected(2, rows=[('L', 'B', 4)]))
    add('legal', 'lot-order', lines(event('a', lot='z'), event('b', lot='a')),
        expected(2, rows=[('a', 'A', 1), ('z', 'A', 1)]))
    add('legal', 'case-significant', lines(event('a', site='a'), event('b', site='A')),
        expected(2, rows=[('L', 'A', 1), ('L', 'a', 1)]))
    add('legal', 'json-whitespace-crlf', b' \t' + lines(event()).rstrip(b'\n') + b' \r\n',
        expected(1, rows=[('L', 'A', 1)]))
    add('legal', 'balance-beyond-event-bound', lines(event('a', quantity=10**9),
        event('b', quantity=10**9)), expected(2, rows=[('L', 'A', 2 * 10**9)]))
    add('legal', 'no-final-LF', lines(event()).rstrip(b'\n'),
        expected(1, rows=[('L', 'A', 1)]))

    a = event()
    add('identity', 'duplicate', lines(a, a), expected(1, 1, [('L', 'A', 1)]))
    add('identity', 'key-order', lines(a, dict(reversed(list(a.items())))),
        expected(1, 1, [('L', 'A', 1)]))
    add('identity', 'three-occurrences', lines(a, a, a), expected(1, 2, [('L', 'A', 1)]))
    consumed = event('b', 'consume')
    moved = event('b', 'move')
    add('identity', 'consume-after-depletion', lines(a, consumed, consumed), expected(2, 1))
    add('identity', 'move-after-depletion', lines(a, moved, moved),
        expected(2, 1, [('L', 'B', 1)]))
    add('identity', 'quantity-conflict', lines(a, event(quantity=2)))
    add('identity', 'op-conflict', lines(a, event(op='consume')))
    add('identity', 'lot-conflict', lines(a, event(lot='Other')))
    add('identity', 'invalid-duplicate-bool', lines(a, event(quantity=True)))
    add('identity', 'invalid-duplicate-float', lines(a, event(quantity=1.0)))

    add('order', 'consume-empty', lines(event(op='consume')))
    add('order', 'move-empty', lines(event(op='move')))
    add('order', 'consume-insufficient', lines(event(quantity=5), event('b', 'consume', quantity=6)))
    add('order', 'move-insufficient', lines(event(quantity=5), event('b', 'move', quantity=6)))
    add('order', 'future-credit', lines(event('a', 'consume'), event('b')))
    add('order', 'recredit', lines(event('a'), event('b', 'consume'), event('c', quantity=4)),
        expected(3, rows=[('L', 'A', 4)]))
    add('order', 'reverse-empty-origin', lines(event(), event('b', 'move', site='B', to='A')))
    add('order', 'chain', lines(event(quantity=3), event('b', 'move', quantity=3),
        event('c', 'move', site='B', to='C', quantity=2)),
        expected(3, rows=[('L', 'B', 1), ('L', 'C', 2)]))
    add('order', 'same-site', lines(event(), event('b', 'move', to='A')))
    add('order', 'transient-overdraw', lines(event(), event('b', 'consume', quantity=2), event('c')))

    for name, quantity in [('bool', True), ('float', 1.0), ('negative', -1), ('zero', 0),
                           ('over-max', 10**9 + 1), ('string', '1')]:
        add('types', 'quantity-' + name, lines(event(quantity=quantity)))
    add('types', 'unicode-not-normalized', lines(event('a', lot='é'), event('b', lot='e\u0301')),
        expected(2, rows=[('e\u0301', 'A', 1), ('é', 'A', 1)]))
    add('types', 'invalid-utf8', b'\xff\n')
    add('types', 'surrogate-escape', json.dumps(event(lot='\ud800')).encode('ascii') + b'\n')
    add('types', 'nul-escape', lines(event(lot='L\x00')))
    add('types', 'cr-escape', lines(event(lot='L\r')))
    add('types', 'lf-escape', lines(event(lot='L\n')))
    add('types', 'raw-NUL', lines(event()) + b'\x00')

    add('format', 'extra-key', lines(event(extra=1)))
    missing = event(); del missing['site']
    add('format', 'missing-key', lines(missing))
    add('format', 'duplicate-json-key', lines(event()).replace(b'"id":"a"', b'"id":"a","id":"a"'))
    add('format', 'array', '[]\n')
    add('format', 'unknown-op', lines(event(op='adjust')))
    add('format', 'blank-line', b'\n')
    add('format', 'two-final-LF', lines(event()) + b'\n')
    add('format', 'whitespace-line', b' \t\r\n')
    add('format', 'BOM', b'\xef\xbb\xbf' + lines(event()))
    add('format', 'argv', b'', argv=['--help'])
    add('format', 'argv-with-payload', lines(event()), argv=['--help'])
    add('format', 'argv-before-stdin', b'', argv=['--help'])
    result[-1]['stdin_mode'] = 'held_open'
    for suffix,raw in [('NaN',b'NaN\n'),('Infinity',b'Infinity\n')]:
        add('types','bare-'+suffix,raw)
    for token in ('NaN','Infinity','-Infinity'):
        add('types','quantity-'+token,lines(event()).replace(b'"quantity":1',b'"quantity":'+token.encode()))

    string64 = 'é' * 32
    add('boundaries', 'strings-64', lines(event(string64, lot=string64, site=string64)),
        expected(1, rows=[(string64, string64, 1)]))
    add('boundaries', 'string-65', lines(event(lot=string64 + 'a')))
    add('boundaries', 'id-65', lines(event(string64 + 'a')))
    add('boundaries', 'site-65', lines(event(site=string64 + 'a')))
    add('boundaries', 'move-from-to-64', lines(event('a', site=string64, quantity=2),
        event('b', 'move', site=string64, to='t' * 64)),
        expected(2, rows=[('L', 't' * 64, 1), ('L', string64, 1)]))
    add('boundaries', 'move-from-65', lines(event('a', 'move', site=string64 + 'a')))
    add('boundaries', 'move-to-65', lines(event('a'), event('b', 'move', to=string64 + 'a')))
    raw = lines(event())
    boundary = raw[:-1] + b' ' * (65536 - len(raw)) + b'\n'
    assert len(boundary) == 65536
    add('boundaries', 'bytes-65536', boundary, expected(1, rows=[('L', 'A', 1)]))
    add('boundaries', 'bytes-65537', boundary[:-1] + b' \n')
    assert len(raw) * 1001 < 65536
    add('boundaries', 'events-1000', raw * 1000, expected(1, 999, [('L', 'A', 1)]))
    add('boundaries', 'events-1001', raw * 1001)
    base = [event('a', quantity=5), event('b', 'move', quantity=2)]
    add('boundaries', 'metamorphic-base', lines(*base),
        expected(2, rows=[('L', 'A', 3), ('L', 'B', 2)]), relation='base')
    add('boundaries', 'metamorphic-duplicates', lines(*base, *base),
        expected(2, 2, [('L', 'A', 3), ('L', 'B', 2)]), relation='append-identical-events')
    add('boundaries', 'metamorphic-bijection', lines(event('a', lot='Y', site='z', quantity=5),
        event('b', 'move', lot='Y', site='z', to='a', quantity=2)),
        expected(2, rows=[('Y', 'a', 2), ('Y', 'z', 3)]), relation='bijective-lot-site-renaming')
    add('boundaries', 'empty-id', lines(event('')))
    add('boundaries', 'empty-lot', lines(event(lot='')))
    add('boundaries', 'empty-site', lines(event(site='')))
    add('boundaries', 'empty-from', lines(event(op='move', site='')))
    add('boundaries', 'empty-to', lines(event('a'), event('b', 'move', to='')))
    assert len(result) == 80 and len({r['id'] for r in result}) == 80
    assert [sum(r['group'] == g for r in result) for g in GROUPS] == [11, 10, 10, 18, 12, 19]
    return result


def typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(typed_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def judge(recipe, result):
    if result.get('infrastructure_error'):
        return {'status': 'inconclusive', 'reason': result['infrastructure_error']}
    if result['timed_out'] or result['truncated_streams']:
        return {'status': 'fail', 'reason': 'subject resource/stream limit'}
    stdout, stderr = result['stdout'], result['stderr']
    if recipe['expected'] is None:
        passed = result['exit_code'] == 2 and stdout == b'' and stderr == b'{"error":"invalid_input"}\n'
    else:
        try:
            value = strict_json_loads(stdout.decode('utf-8'))
            passed = (result['exit_code'] == 0 and not stderr and stdout.startswith(b'{')
                      and stdout.endswith(b'}\n') and typed_equal(value, recipe['expected']))
        except (ValueError, UnicodeError, RecursionError):
            passed = False
    return {'status': 'pass' if passed else 'fail', 'reason': 'exact typed contract and framing'}
