"""D108 contract checks in memory; no engine, CLI/MCP, preparation outputs.

These checks validate the prospective builder, not generic put semantics or
the underlying physical truth of archived publications.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import types
import unittest

REPO = Path(__file__).resolve().parents[1]
DOSSIER = REPO / "experiments/development/bread_energy_derivation_2026-09-30"


def module(name, relative):
    path = REPO / relative
    loaded = types.ModuleType(name)
    loaded.__file__ = str(path)
    sys.modules[name] = loaded
    exec(compile(path.read_bytes(), str(path), "exec"), loaded.__dict__)
    return loaded


class DocumentaryPreparationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = module("_d108_unit_builder", "scripts/build_bread_energy_variant.py")
        cls.probe = module("_d108_unit_probe", "scripts/probe_bread_energy_variant.py")
        cls.record = json.loads((DOSSIER / "plan_inputs.json").read_bytes())
        cls.scope = json.loads((DOSSIER / "plan.json").read_bytes())["derivation"]
        cls.case = REPO / cls.record["source_case"]["path"]
        cls.raw = (cls.case / "organon.json").read_bytes()
        cls.ledger = json.loads(cls.raw)
        cls.items = {e["payload"]["id"]: copy.deepcopy(e["payload"]) for e in cls.ledger["events"] if e["kind"] == "item_put"}
        cls.claims = json.loads((cls.case / "source_claims.json").read_bytes())
        cls.pdf_pin = cls.builder.pin((cls.case / "source_lca.pdf").read_bytes())

    def derived(self):
        return self.builder.derive(self.items, self.claims, self.pdf_pin, self.scope)

    def test_exact_arithmetic_and_representation_only_error(self):
        result = self.derived()
        self.assertEqual(result["exact_ratio"], {"numerator": 103, "denominator": 184})
        represented = Fraction(result["representation"]["value"])
        error = abs(represented - Fraction(103, 184))
        self.assertEqual(error, Fraction(11, 23 * 10**24))
        self.assertLessEqual(error, Fraction(5, 10**25))
        self.assertTrue(result["representation"]["bound_is_representation_only"])
        self.assertFalse(result["physical_source_truth_authenticated"])

    def test_four_guarded_additions_have_explicit_causal_lineage(self):
        result = self.derived()
        result["derivation_performed_at_utc"] = "2026-09-30T23:59:00+00:00"
        raw = self.builder.encode(result)
        manifest = self.builder.prepare_manifest(self.items, result, hashlib.sha256(raw).hexdigest())
        self.assertEqual([step["id"] for step in manifest["steps"]], list(self.builder.NEW_IDS))
        sources = {"e_piece_mass", "e_bakery_electricity", "e_bakery_natural_gas"}
        self.assertTrue(sources.issubset(manifest["steps"][0]["expected_deps"]))
        known = {key: item["version"] for key, item in self.items.items()}
        for step in manifest["steps"]:
            self.assertEqual(step["expected_version"], 0)
            self.assertEqual(step["expected_deps"], {ref: known[ref] for ref in step["refs"]})
            known[step["id"]] = 1
        evidence, indicator = manifest["steps"][2]["data"], manifest["steps"][3]["data"]
        self.assertEqual(evidence["metric_key"], indicator["metric"])
        self.assertEqual(evidence["value"], indicator["value"])
        self.assertEqual(evidence["unit"], indicator["unit"])
        self.assertEqual(evidence["date"], "2026-09-30")
        self.assertEqual(evidence["source_publication_date"], "2018-12-21")
        self.assertEqual(evidence["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotIn("calculation", evidence)

    def test_preparation_negatives_are_in_memory_and_source_unchanged(self):
        before = copy.deepcopy(self.items)
        rows = self.probe.preparation_negatives(self.builder, self.items, self.claims, self.pdf_pin, self.scope, self.raw)
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(row["rejected"] and row["ledger_writes"] == 0 for row in rows))
        self.assertEqual(self.items, before)
        self.assertEqual((self.case / "organon.json").read_bytes(), self.raw)

    def test_json_duplicate_and_nonfinite_input_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'):
            with self.assertRaises(ValueError):
                self.builder.decode(raw)


if __name__ == "__main__":
    unittest.main()
