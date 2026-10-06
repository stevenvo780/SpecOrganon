"""Public contract battery; all fixtures and references are contained here."""
import copy
import itertools
import json
from pathlib import Path
import runpy
import subprocess
import sys
import unittest

P = str(Path(__file__).resolve().with_name('topo_plan.py'))
S = runpy.run_path(P, run_name='subject')
LIMIT = 131072
ERROR = b'topo-plan: invalid input\n'


def enc(x):
    return json.dumps(x, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def ref(r):
    parents = {n: set() for n in r['nodes']}
    for a, b in r['edges']:
        parents[b].add(a)
    order, layers = [], []
    for rounds in (False, True):
        left, done = set(parents), set()
        while left:
            ready = sorted(n for n in left if parents[n] <= done)
            if not ready:
                raise ValueError('cycle')
            chosen = ready if rounds else ready[:1]
            if rounds:
                layers.append(chosen)
            else:
                order.extend(chosen)
            left.difference_update(chosen)
            done.update(chosen)
    return dict(order=order, layers=layers, roots=layers[0] if layers else [])


def pairs(items):
    result = {}
    for k, v in items:
        if k in result:
            raise ValueError('duplicate output key')
        result[k] = v
    return result


def constant(x):
    raise ValueError('nonfinite output')


class Tests(unittest.TestCase):
    def cli(self, data):
        return subprocess.run([sys.executable, '-I', '-B', P], input=data,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

    def decoded(self, data, count):
        self.assertTrue(data.endswith(b'\n') if count else data == b'')
        lines = data.split(b'\n')[:-1] if data else []
        self.assertEqual(len(lines), count)
        out = [json.loads(x.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=constant) for x in lines]
        for x in out:
            self.assertTrue(isinstance(x, dict))
            self.assertEqual(set(x), {'order', 'layers', 'roots'})
        return out

    def valid(self, data, expected):
        p = self.cli(data)
        self.assertEqual(p.returncode, 0)
        self.assertTrue(p.stderr == b'')
        self.assertTrue(self.decoded(p.stdout, len(expected)) == expected,
                        'semantic output mismatch')

    def invalid(self, data):
        p = self.cli(data)
        self.assertEqual(p.returncode, 2)
        self.assertTrue(p.stdout == b'', 'non-atomic invalid batch')
        self.assertTrue(p.stderr == ERROR, 'incorrect error bytes')

    def batch(self, requests):
        self.valid(b'\n'.join(map(enc, requests)), [ref(r) for r in requests])

    def test_examples_framing(self):
        r = [dict(nodes=['z', 'b', 'a'], edges=[['a', 'b']]),
             dict(nodes=['c', 'a', 'b'], edges=[['a', 'c'], ['b', 'c'], ['a', 'c']]),
             dict(nodes=[], edges=[])]
        expected = [dict(order=['a', 'b', 'z'], layers=[['a', 'z'], ['b']], roots=['a', 'z']),
                    dict(order=['a', 'b', 'c'], layers=[['a', 'b'], ['c']], roots=['a', 'b']),
                    dict(order=[], layers=[], roots=[])]
        self.valid(b'', [])
        self.valid(b'\n'.join(map(enc, r)) + b'\n', expected)
        self.valid(b'\r\n'.join(map(enc, r)), expected)
        self.valid(b' \t' + enc(r[0]) + b' \t\r\n', expected[:1])

    def test_exhaustive_four_nodes(self):
        nodes = ['d', 'a', 'c', 'b']
        possible = list(itertools.permutations(nodes, 2))
        dags, cycles = [], 0
        for mask in range(4096):
            r = dict(nodes=nodes[:], edges=[list(e) for i, e in enumerate(possible)
                                          if mask & (1 << i)])
            before = copy.deepcopy(r)
            try:
                expected = ref(r)
            except ValueError:
                cycles += 1
                with self.assertRaises(ValueError):
                    S['process'](enc(r))
            else:
                actual = self.decoded(S['process'](enc(r)).encode('utf-8'), 1)
                self.assertTrue(actual == [expected], 'DAG mask %d' % mask)
                self.assertTrue(S['plan'](r) == expected)
                dags.append(r)
            self.assertTrue(r == before, 'input mutated')
        self.assertEqual(len(dags), 543)
        self.assertEqual(cycles, 3553)
        for start in range(0, len(dags), 100):
            self.batch(dags[start:start + 100])

    def test_permutations(self):
        edges = [['a', 'b'], ['b', 'c'], ['a', 'c']]
        requests = [dict(nodes=list(ns), edges=list(es) + [es[0], es[0]])
                    for ns in itertools.permutations(['a', 'b', 'c', 'z'])
                    for es in itertools.permutations(edges)]
        requests.append(dict(nodes=['a_', 'a0', 'a', 'a' + '0' * 15], edges=[]))
        self.batch(requests)

    def test_limits(self):
        ns = ['n%d' % i for i in range(120)]
        chain = dict(nodes=ns, edges=[[ns[i], ns[i + 1]] for i in range(119)])
        dense = dict(nodes=ns, edges=[[ns[i], ns[j]] for i in range(120)
                                    for j in range(i + 1, 120)][:2000])
        duplicate = dict(nodes=['a', 'b'], edges=[['a', 'b']] * 2000)
        self.batch([chain, dense, duplicate])
        self.invalid(enc(dict(nodes=ns + ['extra'], edges=[])))
        self.invalid(enc(dict(nodes=['a', 'b'], edges=[['a', 'b']] * 2001)))
        empty = dict(nodes=[], edges=[])
        line = enc(empty)
        padded = b' ' * (LIMIT - len(line) - 1) + line + b'\n'
        self.assertEqual(len(padded), LIMIT)
        self.valid(padded, [ref(empty)])
        self.invalid(b' ' + padded)
        count = LIMIT // (len(line) + 1)
        self.valid((line + b'\n') * count, [ref(empty)] * count)

    def test_invalid_shapes(self):
        cases = [None, True, 0, 'x', [], {}, dict(nodes=[]), dict(edges=[]),
                 dict(nodes=[], edges=[], extra=1)]
        for v in [None, {}, 'a', 0, False]:
            cases.extend([dict(nodes=v, edges=[]), dict(nodes=[], edges=v)])
        for n in ['', 'A', '0a', '_a', 'a-b', 'a b', 'a\n', 'a' * 17,
                  'é', 'aé', 'ａ', '\ud800', None, False, 1, [], {}]:
            cases.append(dict(nodes=[n], edges=[]))
        cases.append(dict(nodes=['a', 'a'], edges=[]))
        for e in [None, 1, False, {}, 'ab', [], ['a'], ['a', 'b', 'a'],
                  [[], 'b'], ['a', {}], [True, 'b'], ['a', 1],
                  ['unknown', 'b'], ['a', 'unknown'], ['a', 'a']]:
            cases.append(dict(nodes=['a', 'b'], edges=[e]))
        cases.extend([dict(nodes=['a', 'b'], edges=[['a', 'b'], ['b', 'a']]),
                      dict(nodes=['a', 'b', 'c', 'z'],
                           edges=[['a', 'b'], ['b', 'c'], ['c', 'a']])])
        prefix = enc(dict(nodes=['z', 'b', 'a'], edges=[['a', 'b']])) + b'\n'
        for i, r in enumerate(cases):
            with self.subTest(case=i):
                self.invalid(enc(r))
                self.invalid(prefix + enc(r))

    def test_invalid_syntax_encoding(self):
        cases = [b'\n', b'\r\n', b' ', b'\t\n', b'{', b'{} garbage',
                 b'{"nodes":[],"edges":[],}',
                 b'{"nodes":[],"nodes":[],"edges":[]}',
                 b'{"nodes":[],"edges":[],"edg\\u0065s":[]}',
                 b'{"nodes":[{"x":1,"x":2}],"edges":[]}',
                 b'{"nodes":NaN,"edges":[]}',
                 b'{"nodes":[],"edges":Infinity}',
                 b'{"nodes":[],"edges":-Infinity}',
                 b'{"nodes":[1e999],"edges":[]}',
                 b'\xef\xbb\xbf{"nodes":[],"edges":[]}',
                 b'\xff', b'\xc0\xaf', b'\xed\xa0\x80', b'\xe2\x82',
                 b'{"nodes":["\xff"],"edges":[]}',
                 b'{"nodes":' + b'[' * 2000 + b']' * 2000 + b',"edges":[]}']
        good = enc(dict(nodes=[], edges=[]))
        cases.extend([good + b' {}', good + b'\n\n', good + b'\n \n',
                      good + b'\r' + good, good + '\u2028'.encode('utf-8') + good])
        for i, data in enumerate(cases):
            with self.subTest(case=i):
                self.invalid(data)
                self.invalid(good + b'\n' + data)


if __name__ == '__main__':
    unittest.main(verbosity=1)
