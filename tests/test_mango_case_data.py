"""Guard the published load transcription against seed/ledger drift."""

import json
from decimal import Decimal
from pathlib import Path

from specorganon.ledger import read_project


CASE = Path(__file__).resolve().parents[1] / "cases" / "mango"
TABLE15_IDS = (
    "e_P1_table15_sorting",
    "e_P2_table15_transport",
    "e_P3_table15_ripening",
)
PRE_APPEND_HEAD = "5a0bd44b7276928826090a57f7fad5c2994792a29f1df3fc8603db30331564e7"


def test_mango_table15_loads_match_source_transcription_and_appended_ledger() -> None:
    source = json.loads((CASE / "fao_table15_loads.json").read_text(encoding="utf-8"))
    seed = json.loads((CASE / "seed.json").read_text(encoding="utf-8"))
    ledger = read_project(CASE)

    assert ledger["events"][26]["hash"] == PRE_APPEND_HEAD
    assert ledger["events"][27]["prev_hash"] == PRE_APPEND_HEAD
    assert tuple(item["id"] for item in seed["items"][23:26]) == TABLE15_IDS
    assert tuple(event["payload"]["id"] for event in ledger["events"][27:30]) == TABLE15_IDS
    assert len({row["local_row_id"] for row in source["loads"]}) == 3

    scopes = set()
    for row, item, event in zip(source["loads"], seed["items"][23:26], ledger["events"][27:30]):
        data = item["data"]
        assert item["kind"] == "evidence"
        assert item["refs"] == ["b_scope"]
        assert event["kind"] == "item_put"
        assert event["payload"] == {
            "id": item["id"], "kind": item["kind"], "text": item["text"],
            "data": data, "deps": {"b_scope": 1}, "version": 1,
        }
        assert data["origin"] == "published"
        assert data["source"] == source["provenance"]["url"]
        assert data["sha256_source"] == source["provenance"]["pdf_sha256_checked_2026_09_26"]
        assert data["local_row_id"] == row["local_row_id"]
        assert (data["event"], data["location"], data["duration"], data["number_of_units"]) == (
            row["event"], row["location"], row["duration"], row["number_of_units"]
        )
        assert (data["printed_before"], data["printed_after"], data["printed_unit"]) == (
            row["before"], row["after"], row["mass_unit"]
        )
        assert Decimal(str(data["reported_quantity_loss_pct"])) == Decimal(row["reported_quantity_loss_pct"])
        assert Decimal(str(data["value"])) == Decimal(row["reported_quantity_loss_pct"])
        recomputed = (Decimal(row["before"]) - Decimal(row["after"])) * 100 / Decimal(row["before"])
        assert Decimal(str(data["recomputed_from_printed_weights_pct"])) == recomputed.quantize(Decimal("0.00001"))
        assert data["exact_event_date"] is None
        assert data["measurement_uncertainty"] is None
        scopes.add(data["scope"])
    assert len(scopes) == 3
