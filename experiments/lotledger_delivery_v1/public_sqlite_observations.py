"""Public pre-generation primitive observations, not a LotLedger implementation.

Inputs are synthetic fixtures; results are actual SQLite observations. They do
not establish whole JSONL-contract conformance, field utility or method advantage.
"""
import json
import sqlite3
import sys


def connection():
    c = sqlite3.connect(':memory:', isolation_level=None)
    c.execute('CREATE TABLE events (id TEXT PRIMARY KEY, amount INTEGER NOT NULL)')
    c.execute('CREATE TABLE stock (site TEXT PRIMARY KEY, quantity INTEGER CHECK(quantity >= 0))')
    return c


def run():
    observations = []
    def record(identity, actual, expected):
        observations.append({'id': identity, 'actual': actual, 'expected': expected,
                             'passed': actual == expected})
    with connection() as c:
        c.execute("INSERT INTO events VALUES ('fixture-a', 4)")
        rejected = False
        try: c.execute("INSERT INTO events VALUES ('fixture-a', 4)")
        except sqlite3.IntegrityError: rejected = True
        record('primary-key-duplicate', {'rejected': rejected, 'rows': c.execute('SELECT count(*) FROM events').fetchone()[0]},
               {'rejected': True, 'rows': 1})
    with connection() as c:
        c.execute('BEGIN')
        c.execute("INSERT INTO events VALUES ('fixture-a', 4)")
        rejected = False
        try: c.execute("INSERT INTO events VALUES ('fixture-a', 5)")
        except sqlite3.IntegrityError: rejected = True
        record('abort-retains-prior-statement', {'rejected': rejected, 'rows': c.execute('SELECT count(*) FROM events').fetchone()[0], 'in_transaction': c.in_transaction},
               {'rejected': True, 'rows': 1, 'in_transaction': True})
        c.execute('ROLLBACK')
        record('explicit-rollback-whole-transaction', {'rows': c.execute('SELECT count(*) FROM events').fetchone()[0], 'in_transaction': c.in_transaction},
               {'rows': 0, 'in_transaction': False})
    with connection() as c:
        c.execute("INSERT INTO stock VALUES ('fixture-A', 7)")
        rejected = False
        try: c.execute("UPDATE stock SET quantity=-1 WHERE site='fixture-A'")
        except sqlite3.IntegrityError: rejected = True
        record('check-rejects-negative', {'rejected': rejected, 'quantity': c.execute('SELECT quantity FROM stock').fetchone()[0]},
               {'rejected': True, 'quantity': 7})
    with connection() as c:
        c.execute("INSERT INTO stock VALUES ('fixture-A',7),('fixture-B',1)")
        c.execute('BEGIN')
        affected = c.execute("UPDATE stock SET quantity=quantity-3 WHERE site='fixture-A' AND quantity>=3").rowcount
        if affected == 1:
            c.execute("UPDATE stock SET quantity=quantity+3 WHERE site='fixture-B'")
            c.execute('COMMIT')
        else: c.execute('ROLLBACK')
        record('guarded-transfer-conservation', {'affected': affected, 'stocks': c.execute('SELECT site,quantity FROM stock ORDER BY site').fetchall(), 'total': c.execute('SELECT sum(quantity) FROM stock').fetchone()[0]},
               {'affected': 1, 'stocks': [('fixture-A',4),('fixture-B',4)], 'total': 8})
    with connection() as c:
        c.execute("INSERT INTO stock VALUES ('fixture-A',2),('fixture-B',1)")
        c.execute('BEGIN')
        affected = c.execute("UPDATE stock SET quantity=quantity-3 WHERE site='fixture-A' AND quantity>=3").rowcount
        if affected == 0: c.execute('ROLLBACK')
        else:
            c.execute("UPDATE stock SET quantity=quantity+3 WHERE site='fixture-B'")
            c.execute('COMMIT')
        record('insufficient-source-preserves-state', {'affected': affected, 'stocks': c.execute('SELECT site,quantity FROM stock ORDER BY site').fetchall()},
               {'affected': 0, 'stocks': [('fixture-A',2),('fixture-B',1)]})
    return {'schema': 1, 'population': 'six explicitly listed SQLite primitive assertions on synthetic inputs',
            'method': 'Fresh in-memory SQLite connections, SQL statements shown in this script; compare actual queries/errors with prespecified fixture expectations',
            'python': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version, 'observations': observations,
            'metric_key': 'sqlite_primitives_verified', 'unit': 'cases',
            'value': sum(row['passed'] for row in observations),
            'scope': 'SQLite primitive semantics only; not full LotLedger JSONL contract or field efficacy'}


if __name__ == '__main__':
    result = run()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result['value'] == len(result['observations']) else 1)
