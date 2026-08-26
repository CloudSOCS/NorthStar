import json
from pathlib import Path

import pytest

from agents.critic import IngestError, apply_cycle_stamps, map_m1_payload, map_m5_payload

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_map_m5_default_skips_incomplete_but_keeps_liquidated():
    payload = json.loads((FIXTURES / "m5_sample.json").read_text())
    rows = map_m5_payload(
        payload, include_incomplete=False,
        source="fixtures/m5_sample.json", date="2026-06-12",
    )
    names = [r["name"] for r in rows]
    assert "mean_reversion" in names
    assert "regime_adaptive" in names
    assert "mean_reversion_pro" not in names
    liq = next(r for r in rows if r["name"] == "sma_crossover")
    assert liq["verdict"] == "liquidated" and liq["status"] == "killed"
    healthy = next(r for r in rows if r["name"] == "breakout")
    assert healthy["status"] == "survived" and healthy["verdict"] == "healthy"
    dep = next(r for r in rows if r["name"] == "mean_reversion")
    assert dep["status"] == "killed" and dep["verdict"] == "deprecate"
    assert dep["family"] == "mean_reversion"
    sal = next(r for r in rows if r["name"] == "regime_adaptive")
    assert sal["status"] == "salvage" and sal["verdict"] == "graduate_m1"


def test_map_m5_include_incomplete():
    payload = json.loads((FIXTURES / "m5_sample.json").read_text())
    rows = map_m5_payload(
        payload, include_incomplete=True,
        source="fixtures/m5_sample.json", date="2026-06-12",
    )
    pro = next(r for r in rows if r["name"] == "mean_reversion_pro")
    assert pro["status"] == "incomplete"
    assert pro["verdict"] == "unscreened_short"


def test_map_m1_one_entry_per_window():
    payload = json.loads((FIXTURES / "m1_sample.json").read_text())
    rows = map_m1_payload(
        payload, source="fixtures/m1_sample.json", date="2026-08-24",
    )
    assert len(rows) == 2
    by_w = {r["window"]: r for r in rows}
    assert by_w["is"]["status"] == "survived" and by_w["is"]["verdict"] == "m1_pass"
    assert by_w["oos"]["status"] == "killed" and by_w["oos"]["verdict"] == "m1_fail"
    assert by_w["is"]["name"] == "tema_cross"


def test_map_m1_no_data_refuses():
    payload = {
        "candidate": {"name": "x"},
        "registry": "spot",
        "window_scores": [{"window": "oos", "verdict": "no data"}],
    }
    with pytest.raises(IngestError, match="no data"):
        map_m1_payload(payload, source="x", date="2026-08-24")


def test_map_m1_empty_scores_refuses():
    with pytest.raises(IngestError, match="window_scores"):
        map_m1_payload(
            {"candidate": {"name": "x"}, "registry": "spot", "window_scores": []},
            source="x", date="2026-08-24",
        )


def test_apply_cycle_stamps_supersedes_oos_only():
    payload = json.loads((FIXTURES / "m1_sample.json").read_text())
    rows = map_m1_payload(
        payload, source="fixtures/m1_sample.json", date="2026-08-24",
    )
    stamped = apply_cycle_stamps(
        rows,
        version="selectivity_v1",
        supersedes="tema_cross.spot.m5.2026-06-12",
        core_idea="Raise mr_entry_z to 2.5.",
    )
    by_w = {r["window"]: r for r in stamped}
    assert by_w["is"]["version"] == "selectivity_v1"
    assert "supersedes" not in by_w["is"]
    assert by_w["oos"]["supersedes"] == "tema_cross.spot.m5.2026-06-12"
    assert by_w["oos"]["id"] == "tema_cross.spot.m1.oos.selectivity_v1.2026-08-24"
    assert by_w["is"]["core_idea"] == "Raise mr_entry_z to 2.5."


def test_apply_cycle_stamps_rejects_missing_supersedes_window():
    payload = json.loads((FIXTURES / "m1_sample.json").read_text())
    rows = map_m1_payload(
        payload, source="fixtures/m1_sample.json", date="2026-08-24",
    )
    with pytest.raises(IngestError, match="supersedes_window"):
        apply_cycle_stamps(
            rows,
            version="selectivity_v1",
            supersedes="tema_cross.spot.m5.2026-06-12",
            supersedes_window="holdout",
        )
