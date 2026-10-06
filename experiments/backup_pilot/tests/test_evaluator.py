import unittest
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

try:
    from evaluator import evaluate
except ImportError:
    evaluate = None

class TestEvaluator(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).parent / 'fixtures'
        
    def test_evaluate_missing_candidate(self):
        result = evaluate(Path('/nonexistent/path/to/backup.py'), variant='V1', stage=1, seed=42)
        self.assertEqual(result['score'], 0)
        self.assertIn('critical_failures', result)

    def test_false_success_candidate(self):
        candidate = self.fixtures_dir / 'false_success.py'
        result = evaluate(candidate, variant='V1', stage=1, seed=42)
        self.assertLess(result['score'], 1.0)
        # False success in roundtrip isn't necessarily a critical failure, just a normal failure
        # So we just ensure it didn't score 1.0

    def test_silent_corruption_candidate(self):
        candidate = self.fixtures_dir / 'silent_corruption.py'
        result = evaluate(candidate, variant='V1', stage=1, seed=42)
        # It mutates source and dest, so 'source_intact' and 'dest_protected' should be critical failures
        self.assertTrue(any('source_intact' in str(f) or 'dest_protected' in str(f) for f in result['critical_failures']))

    def test_stage2_ignore_max_bytes(self):
        candidate = self.fixtures_dir / 'ignore_max_bytes.py'
        result = evaluate(candidate, variant='V1', stage=2, seed=42)
        self.assertLess(result['score'], 1.0)

    def test_sigkill_interruption(self):
        candidate = self.fixtures_dir / 'sigkill_create.py'
        result = evaluate(candidate, variant='V3', stage=1, seed=42)
        self.assertIsNotNone(result)

if __name__ == '__main__':
    unittest.main()
