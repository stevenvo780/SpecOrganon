"""Observable report content and read-only behavior on actual ledgers."""

from specorganon import engine
from specorganon.report import case_report


def test_report_preserves_ledger_and_shows_pending_work(tmp_path):
    engine.create_case(tmp_path, "Entrada de uso", "desarrollo", "agent:author")
    before = (tmp_path / "organon.json").read_bytes()
    report = case_report(tmp_path)
    assert report["next"]["action"] == "create_artifacts"
    assert report["accepted_phases"] == 0
    assert report["artifact_count"] == 0
    assert "frame" in report["markdown"]
    assert (tmp_path / "organon.json").read_bytes() == before


def test_report_tracks_versioned_refs_and_changed_premise(tmp_path):
    engine.create_case(tmp_path, "Premisa revisada", "desarrollo", "agent:author")
    engine.put_item(tmp_path, "p1", "problem", "Primera formulación", [], {}, "agent:author")
    engine.put_item(tmp_path, "s1", "assumption", "Depende del problema", ["p1"], {}, "agent:author")
    engine.put_item(tmp_path, "p1", "problem", "Nueva formulación", [], {}, "agent:author")
    before = (tmp_path / "organon.json").read_bytes()
    report = case_report(tmp_path)
    assert report["artifact_count"] == 2
    assert "Depende de: p1 v1." in report["markdown"]
    assert "Sus dependencias cambiaron" in report["markdown"]
    assert "Nueva formulación" in report["markdown"]
    assert (tmp_path / "organon.json").read_bytes() == before


def test_report_displays_test_failure_and_scoped_verdict(tmp_path):
    engine.create_case(tmp_path, "Prueba fallida", "desarrollo", "agent:author")
    engine.put_item(tmp_path, "t1", "test", "Comando falló", [], {"passed": False, "command": "false"}, "agent:author")
    engine.put_item(tmp_path, "a1", "assessment", "No demostró eficacia", [], {
        "verdict": "no_demostrado", "claim_scope": "technical", "uncertainty": "Falta solución",
        "adverse_effects": "Sin intervención", "cost": "Sin gasto adicional",
    }, "agent:author")
    report = case_report(tmp_path)
    assert "signed test needs a current successful signed execution receipt" in report["markdown"]
    assert '"verdict": "no_demostrado"' in report["markdown"]
    assert '"claim_scope": "technical"' in report["markdown"]
    assert report["accepted_phases"] == 0


def test_report_keeps_user_data_inside_escaped_text_and_json(tmp_path):
    engine.create_case(tmp_path, "<script>malformed | title</script>", "desarrollo", "agent:author")
    engine.put_item(tmp_path, "p1", "problem", "[link](bad)\n# injected", [], {"note": "```\n# close"}, "agent:author")
    report = case_report(tmp_path)
    assert "\\<script\\>" in report["markdown"]
    assert "[link](bad)" not in report["markdown"]
    assert "````json" in report["markdown"]
    assert "````\n" in report["markdown"]


def test_report_uses_one_snapshot_when_external_trust_changes(tmp_path, monkeypatch):
    monkeypatch.delenv("ORGANON_APPROVERS_FILE", raising=False)
    engine.create_case(tmp_path, "Confianza cambiante", "desarrollo", "human:owner", approval_policy="local")
    engine.put_item(tmp_path, "p1", "problem", "Problema", [], {}, "agent:author")
    engine.put_item(tmp_path, "a1", "actor", "Afectados", ["p1"], {}, "agent:author")
    engine.put_item(tmp_path, "b1", "boundary", "Frontera", ["p1"], {}, "agent:author")
    engine.review_phase(tmp_path, "frame", "accept", "Revisión técnica de los artefactos", "agent:reviewer")
    engine.advance(tmp_path, "frame", "agent:author")
    original = engine.get_state
    reads = []

    def change_trust_after_read(path):
        snapshot = original(path)
        reads.append(snapshot)
        monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(tmp_path / "absent-registry.json"))
        return snapshot

    before = (tmp_path / "organon.json").read_bytes()
    monkeypatch.setattr(engine, "get_state", change_trust_after_read)
    report = case_report(tmp_path)
    assert len(reads) == 1
    assert report["accepted_phases"] == 1
    assert report["next"]["phase"] == "critique"
    current = original(tmp_path)
    assert current["revision"] == report["revision"]
    assert not current["phases"]["frame"]["accepted"]
    assert (tmp_path / "organon.json").read_bytes() == before
