"""Public stdlib capability probes, specified before execution; not CSVShape."""
import csv
import io
import json
import sys


PROBES = [
    ('quoted-comma', 'x,y\n"a,b",c\n', [['x', 'y'], ['a,b', 'c']]),
    ('quoted-newline', 'x\n"a\nb"\n', [['x'], ['a\nb']]),
    ('escaped-quote', 'x\n"a""b"\n', [['x'], ['a"b']]),
    ('strict-unclosed', 'x\n"a\n', 'csv.Error'),
    ('crlf', 'x,y\r\na,b\r\n', [['x', 'y'], ['a', 'b']]),
    ('strings-without-casts', 'x,y\n1,True\n', [['x', 'y'], ['1', 'True']]),
]


def main():
    rows = []
    for identity, text, expected in PROBES:
        try: observed = list(csv.reader(io.StringIO(text, newline=''), dialect='excel', strict=True, delimiter=','))
        except csv.Error: observed = 'csv.Error'
        rows.append({'id': identity, 'input': text, 'expected': expected, 'observed': observed, 'passed': observed == expected})
    passed = sum(r['passed'] for r in rows)
    result = {'schema': 1, 'scope': 'Six deterministic public stdlib parser probes; no CSVShape programme, field effect or reserved result',
              'python': sys.version.split()[0], 'measurements': {'metric': 'checks_passed_percent', 'unit': 'percent',
              'value': 100 * passed / len(rows), 'passed': passed, 'denominator': len(rows), 'sample_size': len(rows)},
              'uncertainty': 'Exact enumerated probe proportion; no sampling confidence interval or population estimate', 'rows': rows}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if passed == len(rows) else 2


if __name__ == '__main__': raise SystemExit(main())
