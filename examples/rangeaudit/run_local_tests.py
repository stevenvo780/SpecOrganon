"""Adapt original container test paths without modifying the sealed test bytes."""
from pathlib import Path
import runpy
import sys
import unittest

original = Path(__file__).with_name("test_range_audit.py")
namespace = runpy.run_path(str(original), run_name="rangeaudit_original_tests")
case = namespace["RangeAuditContract"]
case.run_batch.__globals__["PYTHON"] = sys.executable
case.run_batch.__globals__["PROGRAM"] = str(original.with_name("range_audit.py"))
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(case))
raise SystemExit(0 if result.wasSuccessful() else 1)
