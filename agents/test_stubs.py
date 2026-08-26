import pytest

from agents.generator import propose_experiment, propose_strategy, require_graph
from agents.hypothesis_graph import append_entry, empty_graph
from agents.post_mortem import lessons_from_live_logs


def _entry(**overrides):
    base = {
        "id": "x.spot.m5.2026-06-12",
        "name": "x",
        "version": "defaults",
        "family": "misc",
        "core_idea": "t",
        "status": "killed",
        "failure_reason": "t",
        "regime_or_period": "t",
        "metrics": {},
        "lesson": "t",
        "date": "2026-06-12",
        "harness": "m5",
        "verdict": "deprecate",
        "source": "t",
        "registry": "spot",
        "window": "is+oos",
        "direction": "long",
    }
    base.update(overrides)
    return base


def test_stubs_load_graph_then_refuse():
    g = require_graph()
    assert g["schema_version"] == 1
    with pytest.raises(NotImplementedError, match="graph"):
        propose_strategy(family="mean_reversion")
    with pytest.raises(NotImplementedError):
        lessons_from_live_logs("/nope")


def test_propose_strategy_calls_relevant(monkeypatch):
    calls = []

    def fake_relevant(g, *, family=None, status=None, include_obsolete=False):
        calls.append({"family": family, "status": status, "include_obsolete": include_obsolete})
        return []

    monkeypatch.setattr("agents.generator.relevant", fake_relevant)
    with pytest.raises(NotImplementedError):
        propose_strategy(family="mean_reversion")
    assert len(calls) == 1
    assert calls[0]["family"] == "mean_reversion"


def test_propose_experiment_stop_on_committed_graph():
    hit = propose_experiment()
    assert hit["action"] == "stop"
    assert hit["supersedes"] is None


def test_propose_experiment_incomplete_short_before_salvage():
    g = empty_graph(updated="2026-08-26")
    g = append_entry(g, _entry(
        id="mean_reversion_pro.spot.m5.2026-06-12",
        name="mean_reversion_pro",
        family="mean_reversion",
        status="incomplete",
        verdict="unscreened_short",
        failure_reason="short unmeasured",
        lesson="Re-screen --direction short.",
    ))
    g = append_entry(g, _entry(
        id="tema_cross.spot.m5.2026-06-12",
        name="tema_cross",
        family="trend",
        status="salvage",
        verdict="graduate_m1",
        failure_reason="fee drag",
        lesson="raise selectivity",
    ))
    hit = propose_experiment(g)
    assert hit["action"] == "run-m1"
    assert hit["strategy"] == "mean_reversion_pro"
    assert hit["direction"] == "short"
    assert hit["supersedes"] is None


def test_propose_experiment_held_out_before_new_salvage():
    g = empty_graph(updated="2026-08-26")
    g = append_entry(g, _entry(
        id="breakout.futures.m1.is.selectivity_v1.2026-08-24",
        name="breakout",
        version="selectivity_v1",
        family="breakout",
        status="survived",
        verdict="m1_pass",
        harness="m1",
        window="is",
        registry="futures",
        failure_reason="survived",
        lesson="t",
    ))
    g = append_entry(g, _entry(
        id="breakout.futures.m1.oos.selectivity_v1.2026-08-24",
        name="breakout",
        version="selectivity_v1",
        family="breakout",
        status="survived",
        verdict="m1_pass",
        harness="m1",
        window="oos",
        registry="futures",
        failure_reason="survived",
        lesson="t",
    ))
    g = append_entry(g, _entry(
        id="tema_cross.spot.m5.2026-06-12",
        name="tema_cross",
        family="trend",
        status="salvage",
        verdict="graduate_m1",
        failure_reason="fee drag",
        lesson="raise selectivity",
    ))
    hit = propose_experiment(g)
    assert hit["action"] == "run-m1"
    assert hit["strategy"] == "breakout"
    assert hit["windows"] == "2023,2024,2025H1"
    assert hit["supersedes"] is None
    assert hit["version"] == "selectivity_v1"


def test_propose_experiment_open_salvage():
    g = empty_graph(updated="2026-08-26")
    g = append_entry(g, _entry(
        id="tema_cross.spot.m5.2026-06-12",
        name="tema_cross",
        family="trend",
        status="salvage",
        verdict="graduate_m1",
        failure_reason="fee drag",
        lesson="raise selectivity",
    ))
    hit = propose_experiment(g)
    assert hit["action"] == "selectivity_m1"
    assert hit["strategy"] == "tema_cross"
    assert hit["supersedes"] == "tema_cross.spot.m5.2026-06-12"
    assert hit["params"] is None


def test_stubs_load_graph_then_refuse():
    g = require_graph()
    assert g["schema_version"] == 1
    with pytest.raises(NotImplementedError, match="graph"):
        propose_strategy(family="mean_reversion")
    with pytest.raises(NotImplementedError):
        lessons_from_live_logs("/nope")


def test_propose_strategy_calls_relevant(monkeypatch):
    calls = []

    def fake_relevant(g, *, family=None, status=None, include_obsolete=False):
        calls.append({"family": family, "status": status, "include_obsolete": include_obsolete})
        return []

    monkeypatch.setattr("agents.generator.relevant", fake_relevant)
    with pytest.raises(NotImplementedError):
        propose_strategy(family="mean_reversion")
    assert len(calls) == 1
    assert calls[0]["family"] == "mean_reversion"
