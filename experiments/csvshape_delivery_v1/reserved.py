"""Prospective CSVShape recipes. Never mounted to authors, reviewers or subjects."""
from __future__ import annotations

import json

from specorganon.ledger import strict_json_loads


def summary(rows, columns):
    return {'rows': rows, 'columns': [dict(zip(('name', 'empty', 'distinct'), c)) for c in columns]}


def recipes():
    result = []
    def add(identity, raw, expected=None, argv=(), public=False):
        if isinstance(raw, str): raw = raw.encode('utf-8')
        result.append({'id': identity, 'stdin_hex': raw.hex(), 'argv': list(argv),
                       'expected': expected, 'public': public})
    add('public-1', 'id,name\na,Ana\nb,\n', summary(2, [('id', 0, 2), ('name', 1, 2)]), public=True)
    add('public-2', 'tag,note\nx,"uno,dos"\ny,"línea1\nlínea2"\n',
        summary(2, [('tag', 0, 2), ('note', 0, 2)]), public=True)
    add('header-only', 'x,y\n', summary(0, [('x', 0, 0), ('y', 0, 0)]))
    add('no-final-newline', 'x\na', summary(1, [('x', 0, 1)]))
    add('repeat-empty', 'x,y\n,1\n,1\nz,\n', summary(3, [('x', 2, 2), ('y', 1, 2)]))
    add('unicode-exact-é', 'x\né\ne\u0301\né\n', summary(3, [('x', 0, 2)]))
    add('names-significant', ' x,x ,\t\n1,2,3\n', summary(1, [(' x', 0, 1), ('x ', 0, 1), ('\t', 0, 1)]))
    add('quoted-header-comma', '"a,b",c\nx,y\n', summary(1, [('a,b', 0, 1), ('c', 0, 1)]))
    add('escaped-quote', 'x\n"a""b"\n', summary(1, [('x', 0, 1)]))
    add('bare-quote-reader-contract', 'x\na"b\n', summary(1, [('x', 0, 1)]))
    add('quoted-empty', 'x\n""\n', summary(1, [('x', 1, 1)]))
    add('crlf', 'x,y\r\na,b\r\n', summary(1, [('x', 0, 1), ('y', 0, 1)]))
    add('semicolon', 'x;y\n1;2\n', summary(1, [('x', 0, 1), ('y', 0, 1)]), ('--delimiter', ';'))
    add('tab', 'x\ty\n1\t2\n', summary(1, [('x', 0, 1), ('y', 0, 1)]), ('--delimiter', '\t'))
    add('explicit-comma', 'x,y\n1,2\n', summary(1, [('x', 0, 1), ('y', 0, 1)]), ('--delimiter', ','))
    for identity, raw in [('empty', b''), ('blank-header', '\n'), ('empty-header-field', ',x\n'),
                          ('duplicate-header', 'x,x\n'), ('blank-data-row', 'x\n\n'),
                          ('short-row', 'x,y\n1\n'), ('wide-row', 'x\n1,2\n'),
                          ('unclosed-quote', 'x\n"a\n'), ('text-after-quote', 'x\n"a"b\n'),
                          ('bom', b'\xef\xbb\xbfx\n'), ('nul', b'x\na\0b\n'),
                          ('invalid-utf8', b'x\n\xff\n'), ('header-lf', '"x\ny"\n'),
                          ('header-cr', '"x\ry"\n')]:
        add(identity, raw)
    for identity, argv in [('unknown', ['--wat']), ('positional', ['data.csv']),
                           ('missing-token', ['--delimiter']), ('equals', ['--delimiter=;']),
                           ('duplicate-option', ['--delimiter', ',', '--delimiter', ';']),
                           ('bad-delimiter', ['--delimiter', '|']), ('long-delimiter', ['--delimiter', ';;']),
                           ('empty-delimiter', ['--delimiter', '']), ('help-is-unknown', ['--help'])]:
        add('argv-' + identity, 'x\n', argv=argv)
    for count in (32, 33):
        names = ['c' + str(i) for i in range(count)]
        add('columns-' + str(count), ','.join(names) + '\n',
            summary(0, [(n, 0, 0) for n in names]) if count == 32 else None)
    for size in (64, 65):
        name = 'é' * (size // 2) + ('a' if size % 2 else '')
        add('header-bytes-' + str(size), name + '\n', summary(0, [(name, 0, 0)]) if size == 64 else None)
    for count in (1000, 1001):
        add('rows-' + str(count), 'x\n' + 'a\n' * count,
            summary(count, [('x', 0, 1)]) if count == 1000 else None)
    for size in (4096, 4097):
        field = 'é' * (size // 2) + ('a' if size % 2 else '')
        add('field-bytes-' + str(size), 'x\n' + field + '\n',
            summary(1, [('x', 0, 1)]) if size == 4096 else None)
    boundary = 'x\n' + ('a' * 4095 + '\n') * 15 + 'b' * 4093 + '\n'
    assert len(boundary.encode()) == 65536
    add('input-bytes-65536', boundary, summary(16, [('x', 0, 2)]))
    add('input-bytes-65537', boundary[:-1] + 'b\n')
    assert len(result) == 48 and len({r['id'] for r in result}) == 48
    return result


def typed_equal(left, right):
    if type(left) is not type(right): return False
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
    if recipe['expected'] is None:
        passed = result['exit_code'] == 2 and result['stdout'] == b'' and result['stderr'] == b'{"error":"invalid_input"}\n'
    else:
        try:
            value = strict_json_loads(result['stdout'].decode('utf-8'))
            passed = (result['exit_code'] == 0 and not result['stderr'] and result['stdout'].endswith(b'\n')
                      and typed_equal(value, recipe['expected']))
        except (ValueError, UnicodeError, RecursionError): passed = False
    return {'status': 'pass' if passed else 'fail', 'reason': 'exact typed contract and framing'}
