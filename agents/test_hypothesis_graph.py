import json
from pathlib import Path

import pytest

from agents.hypothesis_graph import (
    DEFAULT_PATH,
    GraphError,
    append_entry,
    empty_graph,
    load_graph,
    relevant,
    save_graph,
    status_summary,
    validate_entry,
)


def _minimal_entry(**overrides):
    base = {
        "id": "mean_reversion.spot.m5.2026-06-12",
        "name": "mean_reversion",
        "version": "defaults",
        "family": "mean_reversion",
        "core_idea": "Fade N-sigma deviations from a rolling mean.",
        "status": "killed",
        "failure_reason": "M5 deprecate: gross edge <= 0 under audit fees.",
        "regime_or_period": "IS+OOS BTC/ETH/SOL 1h+4h long",
        "metrics": {"mean_net_ret": -26.87, "trades": 487},
        "lesson": "Naive mean reversion dies in trends and to churn.",
        "date": "2026-06-12",
        "harness": "m5",
        "verdict": "deprecate",
        "source": "docs/research/fee-audit-m5.md",
        "registry": "spot",
        "window": "is+oos",
        "direction": "long",
    }
    base.update(overrides)
    return base


def test_empty_graph_roundtrip(tmp_path):
    path = tmp_path / "g.json"
    g = empty_graph()
    save_graph(g, path)
    loaded = load_graph(path)
    assert loaded["schema_version"] == 1
    assert loaded["entries"] == []
    assert loaded["universe"]["datasets"][0] == ["BTC/USDT", "1h"]


def test_load_rejects_unknown_schema(tmp_path):
    path = tmp_path / "g.json"
    path.write_text(json.dumps({"schema_version": 99, "updated": "2026-08-24", "universe": {}, "entries": []}))
    with pytest.raises(GraphError, match="schema_version"):
        load_graph(path)


def test_load_rejects_corrupt_json(tmp_path):
    path = tmp_path / "g.json"
    path.write_text("{not json")
    with pytest.raises(GraphError):
        load_graph(path)


def test_validate_entry_rejects_bad_status():
    with pytest.raises(GraphError, match="status"):
        validate_entry(_minimal_entry(status="nope"))


def test_validate_entry_rejects_missing_id():
    e = _minimal_entry()
    del e["id"]
    with pytest.raises(GraphError, match="id"):
        validate_entry(e)


def test_append_rejects_duplicate_key():
    g = empty_graph()
    g = append_entry(g, _minimal_entry())
    with pytest.raises(GraphError, match="duplicate"):
        append_entry(g, _minimal_entry(id="other-id"))


def test_append_allows_same_name_different_registry():
    g = empty_graph()
    g = append_entry(g, _minimal_entry())
    g = append_entry(g, _minimal_entry(
        id="momentum.futures.m5.2026-06-12",
        name="momentum",
        family="trend",
        registry="futures",
    ))
    assert len(g["entries"]) == 2


def test_supersede_requires_new_version_and_existing_id():
    g = empty_graph()
    g = append_entry(g, _minimal_entry())
    with pytest.raises(GraphError, match="superseded_by"):
        append_entry(g, _minimal_entry(
            id="mean_reversion.spot.m5.v2",
            version="v2",
            superseded_by="someone",
        ))
    with pytest.raises(GraphError, match="version"):
        append_entry(g, _minimal_entry(
            id="mean_reversion.spot.m5.v2",
            version="defaults",
            supersedes="mean_reversion.spot.m5.2026-06-12",
        ))
    with pytest.raises(GraphError, match="supersedes"):
        append_entry(g, _minimal_entry(
            id="mean_reversion.spot.m5.v2",
            version="v2",
            supersedes="does-not-exist",
        ))
    g = append_entry(g, _minimal_entry(
        id="mean_reversion.spot.m5.v2",
        version="v2",
        supersedes="mean_reversion.spot.m5.2026-06-12",
        failure_reason="survived",
        status="survived",
        verdict="healthy",
    ))
    rows = relevant(g, family="mean_reversion")
    by_id = {r["id"]: r for r in rows}
    old_id = "mean_reversion.spot.m5.2026-06-12"
    new_id = "mean_reversion.spot.m5.v2"
    assert by_id[old_id]["obsolete"] is True
    assert by_id[old_id]["superseded_by"] == new_id
    assert by_id[new_id]["obsolete"] is False
    assert by_id[new_id]["supersedes"] == old_id
    assert by_id[new_id].get("superseded_by") in (None, "")
    # old entry is not deleted; only the pointer is stamped
    assert g["entries"][0]["status"] == "killed"
    assert g["entries"][0]["failure_reason"].startswith("M5 deprecate")
    assert g["entries"][0]["superseded_by"] == new_id


def test_append_rejects_already_superseded_target():
    g = empty_graph()
    g = append_entry(g, _minimal_entry())
    g = append_entry(g, _minimal_entry(
        id="mean_reversion.spot.m5.v2",
        version="v2",
        supersedes="mean_reversion.spot.m5.2026-06-12",
        failure_reason="survived",
        status="survived",
        verdict="healthy",
    ))
    with pytest.raises(GraphError, match="already superseded"):
        append_entry(g, _minimal_entry(
            id="mean_reversion.spot.m5.v3",
            version="v3",
            supersedes="mean_reversion.spot.m5.2026-06-12",
            failure_reason="survived",
            status="survived",
            verdict="healthy",
        ))


def test_append_rejects_duplicate_key_even_with_supersedes():
    g = empty_graph()
    g = append_entry(g, _minimal_entry())
    g = append_entry(g, _minimal_entry(
        id="macd.spot.m5.2026-06-12",
        name="macd",
        family="trend",
        version="other",
    ))
    with pytest.raises(GraphError, match="duplicate"):
        append_entry(g, _minimal_entry(
            id="mean_reversion.spot.m5.clone",
            supersedes="macd.spot.m5.2026-06-12",
        ))


def test_append_rejects_duplicate_id():
    g = empty_graph()
    g = append_entry(g, _minimal_entry())
    with pytest.raises(GraphError, match="id"):
        append_entry(g, _minimal_entry(
            name="vwap_reversion",
            family="mean_reversion",
            registry="spot",
            window="other",
        ))


def test_relevant_filters_family_and_keeps_obsolete():
    g = empty_graph()
    g = append_entry(g, _minimal_entry())
    g = append_entry(g, _minimal_entry(
        id="macd.spot.m5.2026-06-12",
        name="macd",
        family="trend",
    ))
    rows = relevant(g, family="mean_reversion")
    assert [r["name"] for r in rows] == ["mean_reversion"]


def test_status_summary_counts():
    g = empty_graph()
    g = append_entry(g, _minimal_entry())
    s = status_summary(g)
    assert s["by_status"]["killed"] == 1
    assert s["by_family"]["mean_reversion"] == 1
    assert s["n_entries"] == 1


def test_committed_seed_mean_reversion_family():
    g = load_graph(DEFAULT_PATH)
    rows = relevant(g, family="mean_reversion")
    names = {r["name"] for r in rows}
    assert "mean_reversion" in names
    assert "mean_reversion_pro" in names
    naive = next(r for r in rows if r["name"] == "mean_reversion")
    assert naive["status"] == "killed" and naive["verdict"] == "deprecate"
    pro = next(r for r in rows if r["name"] == "mean_reversion_pro")
    assert pro["status"] == "incomplete" and pro["verdict"] == "unscreened_short"
    assert any(r["id"] == "squeeze_momentum.documented.983" for r in g["entries"])
    assert any(r["id"] == "ichimoku_cloud.documented.997" for r in g["entries"])
    # deprecate + 4 graduate_m1 + 1 incomplete + 2 documented
    assert g["schema_version"] == 1
    seed = [e for e in g["entries"] if e["harness"] in ("m5", "documented")]
    assert len(seed) == 27 + 4 + 1 + 2  # 27 deprecate rows, 4 salvage, 1 pro, 2 docs


def test_committed_graph_records_selectivity_v1_cycle():
    g = load_graph(DEFAULT_PATH)
    old_id = "regime_adaptive_htf.spot.m5.2026-06-12"
    oos_id = "regime_adaptive_htf.spot.m1.oos.selectivity_v1.2026-08-24"
    is_id = "regime_adaptive_htf.spot.m1.is.selectivity_v1.2026-08-24"
    old = next(e for e in g["entries"] if e["id"] == old_id)
    oos = next(e for e in g["entries"] if e["id"] == oos_id)
    is_row = next(e for e in g["entries"] if e["id"] == is_id)
    assert old["status"] == "salvage" and old["verdict"] == "graduate_m1"
    assert old["superseded_by"] == oos_id
    assert oos["supersedes"] == old_id
    assert oos["status"] == "survived" and oos["verdict"] == "m1_pass"
    assert "supersedes" not in is_row
    assert oos["source"].startswith("experiments/")
    rows = relevant(g, family="regime")
    by_id = {r["id"]: r for r in rows}
    assert by_id[old_id]["obsolete"] is True
    assert by_id[oos_id]["obsolete"] is False
    for window in ("2023", "2024", "2025H1"):
        row = next(e for e in g["entries"] if e["id"] == (
            f"regime_adaptive_htf.spot.m1.{window}.selectivity_v1.2026-08-24"
        ))
        assert row["status"] == "killed" and row["verdict"] == "m1_fail"
        assert "supersedes" not in row
    assert old["superseded_by"] == oos_id


def test_committed_graph_records_tema_cross_selectivity_v1_cycle():
    g = load_graph(DEFAULT_PATH)
    old_id = "tema_cross.spot.m5.2026-06-12"
    oos_id = "tema_cross.spot.m1.oos.selectivity_v1.2026-08-24"
    is_id = "tema_cross.spot.m1.is.selectivity_v1.2026-08-24"
    old = next(e for e in g["entries"] if e["id"] == old_id)
    oos = next(e for e in g["entries"] if e["id"] == oos_id)
    is_row = next(e for e in g["entries"] if e["id"] == is_id)
    assert old["status"] == "salvage" and old["verdict"] == "graduate_m1"
    assert old["superseded_by"] == oos_id
    assert oos["supersedes"] == old_id
    assert oos["status"] == "killed" and oos["verdict"] == "m1_fail"
    assert is_row["status"] == "killed" and is_row["verdict"] == "m1_fail"
    assert "supersedes" not in is_row
    rows = relevant(g, family="trend")
    by_id = {r["id"]: r for r in rows}
    assert by_id[old_id]["obsolete"] is True
    assert by_id[oos_id]["obsolete"] is False


def test_committed_graph_records_breakout_selectivity_v1_cycle():
    g = load_graph(DEFAULT_PATH)
    old_id = "breakout.futures.m5.2026-06-12"
    oos_id = "breakout.futures.m1.oos.selectivity_v1.2026-08-24"
    is_id = "breakout.futures.m1.is.selectivity_v1.2026-08-24"
    old = next(e for e in g["entries"] if e["id"] == old_id)
    oos = next(e for e in g["entries"] if e["id"] == oos_id)
    is_row = next(e for e in g["entries"] if e["id"] == is_id)
    assert old["status"] == "salvage" and old["verdict"] == "graduate_m1"
    assert old["registry"] == "futures"
    assert old["superseded_by"] == oos_id
    assert oos["supersedes"] == old_id
    assert oos["status"] == "survived" and oos["verdict"] == "m1_pass"
    assert is_row["status"] == "survived" and is_row["verdict"] == "m1_pass"
    assert "supersedes" not in is_row
    rows = relevant(g, family="breakout")
    by_id = {r["id"]: r for r in rows}
    assert by_id[old_id]["obsolete"] is True
    assert by_id[oos_id]["obsolete"] is False
    for window in ("2023", "2024", "2025H1"):
        row = next(e for e in g["entries"] if e["id"] == (
            f"breakout.futures.m1.{window}.selectivity_v1.2026-08-24"
        ))
        assert row["status"] == "killed" and row["verdict"] == "m1_fail"
        assert "supersedes" not in row
    assert old["superseded_by"] == oos_id


def test_committed_graph_records_mean_reversion_pro_short_v1_cycle():
    g = load_graph(DEFAULT_PATH)
    incomplete_id = "mean_reversion_pro.spot.m5.2026-06-12"
    is_id = "mean_reversion_pro.spot.m1.is.short_v1.2026-08-26"
    oos_id = "mean_reversion_pro.spot.m1.oos.short_v1.2026-08-26"
    incomplete = next(e for e in g["entries"] if e["id"] == incomplete_id)
    is_row = next(e for e in g["entries"] if e["id"] == is_id)
    oos = next(e for e in g["entries"] if e["id"] == oos_id)
    assert incomplete["status"] == "incomplete"
    assert incomplete["verdict"] == "unscreened_short"
    assert "superseded_by" not in incomplete
    assert "supersedes" not in is_row and "supersedes" not in oos
    assert is_row["direction"] == "short" and oos["direction"] == "short"
    assert is_row["status"] == "survived" and is_row["verdict"] == "m1_pass"
    assert oos["status"] == "killed" and oos["verdict"] == "m1_fail"
    naive = next(e for e in g["entries"] if e["id"] == "mean_reversion.spot.m5.2026-06-12")
    assert naive["status"] == "killed" and naive["verdict"] == "deprecate"


def test_committed_graph_records_regime_adaptive_selectivity_v1_cycle():
    g = load_graph(DEFAULT_PATH)
    old_id = "regime_adaptive.spot.m5.2026-06-12"
    oos_id = "regime_adaptive.spot.m1.oos.selectivity_v1.2026-08-26"
    is_id = "regime_adaptive.spot.m1.is.selectivity_v1.2026-08-26"
    old = next(e for e in g["entries"] if e["id"] == old_id)
    oos = next(e for e in g["entries"] if e["id"] == oos_id)
    is_row = next(e for e in g["entries"] if e["id"] == is_id)
    assert old["status"] == "salvage" and old["verdict"] == "graduate_m1"
    assert old["superseded_by"] == oos_id
    assert oos["supersedes"] == old_id
    assert oos["status"] == "killed" and oos["verdict"] == "m1_fail"
    assert is_row["status"] == "killed" and is_row["verdict"] == "m1_fail"
    assert "supersedes" not in is_row
