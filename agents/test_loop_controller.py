import json
from pathlib import Path

import pytest

from agents.hypothesis_graph import empty_graph, load_graph, save_graph, append_entry
from agents.loop_controller import main


def test_status_and_relevant(tmp_path, capsys, monkeypatch):
    from agents import loop_controller as lc
    gpath = tmp_path / "g.json"
    # copy seed or a tiny graph
    src = Path("agents/hypothesis_graph.json")
    gpath.write_text(src.read_text())
    monkeypatch.setattr(lc, "GRAPH_PATH", gpath)
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "n_entries=" in out
    assert "killed" in out
    assert main(["relevant", "--family", "mean_reversion"]) == 0
    out = capsys.readouterr().out
    assert "mean_reversion" in out
    assert "mean_reversion_pro" in out


def test_ingest_m5_appends(tmp_path, monkeypatch):
    from agents import loop_controller as lc
    gpath = tmp_path / "g.json"
    save_graph(empty_graph(updated="2026-08-24"), gpath)
    monkeypatch.setattr(lc, "GRAPH_PATH", gpath)
    fixture = Path("agents/fixtures/m5_sample.json")
    assert main(["ingest-m5", "--json", str(fixture)]) == 0
    g = load_graph(gpath)
    names = {e["name"] for e in g["entries"]}
    assert "mean_reversion" in names
    assert "mean_reversion_pro" not in names  # skipped without --include-incomplete
    # Second ingest of the same payload would duplicate keys. Use a one-row
    # incomplete-only payload so --include-incomplete can append pro.
    only_pro = tmp_path / "pro.json"
    payload = json.loads(fixture.read_text())
    payload["rows"] = [r for r in payload["rows"] if r["strategy"] == "mean_reversion_pro"]
    only_pro.write_text(json.dumps(payload))
    assert main(["ingest-m5", "--json", str(only_pro), "--include-incomplete"]) == 0
    g = load_graph(gpath)
    assert any(e["name"] == "mean_reversion_pro" for e in g["entries"])


def test_run_m1_failure_leaves_graph_untouched(tmp_path, monkeypatch):
    from agents import loop_controller as lc
    gpath = tmp_path / "g.json"
    save_graph(empty_graph(updated="2026-08-24"), gpath)
    before = gpath.read_bytes()
    monkeypatch.setattr(lc, "GRAPH_PATH", gpath)
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr(lc, "EXPERIMENTS_ROOT", exp_root)

    class Boom:
        returncode = 1
        stdout = ""
        stderr = "eval failed"

    monkeypatch.setattr(lc, "run_subprocess", lambda argv, timeout: Boom())
    assert main(["run-m1", "--strategy", "tema_cross", "--registry", "spot"]) == 1
    assert gpath.read_bytes() == before
    assert not exp_root.exists()
    assert not list(tmp_path.glob("experiments"))


def test_run_m1_success_ingests(tmp_path, monkeypatch):
    from agents import loop_controller as lc
    gpath = tmp_path / "g.json"
    save_graph(empty_graph(updated="2026-08-24"), gpath)
    monkeypatch.setattr(lc, "GRAPH_PATH", gpath)
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr(lc, "EXPERIMENTS_ROOT", exp_root)
    m1 = json.loads(Path("agents/fixtures/m1_sample.json").read_text())

    def fake_run(argv, timeout):
        json_path = Path(argv[argv.index("--json") + 1])
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(m1))
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(lc, "run_subprocess", fake_run)
    assert main(["run-m1", "--strategy", "tema_cross", "--registry", "spot", "--windows", "is,oos"]) == 0
    g = load_graph(gpath)
    assert any(e["window"] == "oos" and e["verdict"] == "m1_fail" for e in g["entries"])
    copied = next(exp_root.glob("**/m1.json"))
    assert copied.exists()
    assert "spot" in copied.parent.name
    assert "tema_cross" in copied.parent.name
    for e in g["entries"]:
        assert "experiments" in e["source"]
        assert "spot" in e["source"]
        assert "go-trader-m1-" not in e["source"]
        assert "northstar-m1-" not in e["source"]
        assert e["source"] == str(copied)


def test_run_m1_refuses_overwrite_existing_dest(tmp_path, monkeypatch):
    from agents import loop_controller as lc
    gpath = tmp_path / "g.json"
    save_graph(empty_graph(updated="2026-08-24"), gpath)
    monkeypatch.setattr(lc, "GRAPH_PATH", gpath)
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr(lc, "EXPERIMENTS_ROOT", exp_root)
    m1 = json.loads(Path("agents/fixtures/m1_sample.json").read_text())
    call_n = {"n": 0}

    def fake_run(argv, timeout):
        call_n["n"] += 1
        payload = json.loads(json.dumps(m1))
        if call_n["n"] > 1:
            # Distinct bytes so an exist_ok overwrite would be detectable.
            payload["candidate"] = dict(payload.get("candidate") or {}, marker=call_n["n"])
        json_path = Path(argv[argv.index("--json") + 1])
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(payload))
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(lc, "run_subprocess", fake_run)
    assert main(["run-m1", "--strategy", "tema_cross", "--registry", "spot", "--windows", "is,oos"]) == 0
    first = next(exp_root.glob("**/m1.json"))
    first_bytes = first.read_bytes()
    n_entries = len(load_graph(gpath)["entries"])

    assert main(["run-m1", "--strategy", "tema_cross", "--registry", "spot", "--windows", "is,oos"]) == 1
    assert first.read_bytes() == first_bytes
    assert len(load_graph(gpath)["entries"]) == n_entries


def test_run_m1_graph_error_removes_dest(tmp_path, monkeypatch):
    from agents import loop_controller as lc
    from agents.hypothesis_graph import GraphError

    gpath = tmp_path / "g.json"
    save_graph(empty_graph(updated="2026-08-24"), gpath)
    before = gpath.read_bytes()
    monkeypatch.setattr(lc, "GRAPH_PATH", gpath)
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr(lc, "EXPERIMENTS_ROOT", exp_root)
    m1 = json.loads(Path("agents/fixtures/m1_sample.json").read_text())

    def fake_run(argv, timeout):
        json_path = Path(argv[argv.index("--json") + 1])
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(m1))
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(lc, "run_subprocess", fake_run)

    def boom_commit(_entries):
        raise GraphError("duplicate entry id")

    monkeypatch.setattr(lc, "_commit_entries", boom_commit)
    assert main(["run-m1", "--strategy", "tema_cross", "--registry", "spot"]) == 1
    assert gpath.read_bytes() == before
    assert not exp_root.exists() or not any(exp_root.iterdir())


def test_ingest_m1_supersedes_oos_only(tmp_path, monkeypatch):
    from agents import loop_controller as lc

    salvage = {
        "id": "tema_cross.spot.m5.2026-06-12",
        "name": "tema_cross",
        "version": "defaults",
        "family": "trend",
        "core_idea": "Registry strategy tema_cross (spot) at default params.",
        "status": "salvage",
        "failure_reason": "M5 graduate_m1: gross 0.1%/leg but net -0.2%/leg after fees.",
        "regime_or_period": "IS+OOS",
        "metrics": {"mean_net_ret": -0.2, "trades": 10},
        "lesson": "Gross edge exists; raise selectivity before any live consideration.",
        "date": "2026-06-12",
        "harness": "m5",
        "verdict": "graduate_m1",
        "source": "docs/research/fee-audit-m5.md",
        "registry": "spot",
        "window": "is+oos",
        "direction": "long",
    }
    gpath = tmp_path / "g.json"
    save_graph(append_entry(empty_graph(updated="2026-08-24"), salvage), gpath)
    monkeypatch.setattr(lc, "GRAPH_PATH", gpath)
    fixture = Path("agents/fixtures/m1_sample.json")
    assert main([
        "ingest-m1", "--json", str(fixture),
        "--version", "selectivity_v1",
        "--supersedes", "tema_cross.spot.m5.2026-06-12",
        "--core-idea", "Raise mr_entry_z to 2.5.",
    ]) == 0
    g = load_graph(gpath)
    old = next(e for e in g["entries"] if e["id"] == "tema_cross.spot.m5.2026-06-12")
    is_row = next(e for e in g["entries"] if e.get("window") == "is")
    oos = next(e for e in g["entries"] if e.get("window") == "oos")
    assert old["status"] == "salvage"
    assert old["verdict"] == "graduate_m1"
    assert old["superseded_by"] == oos["id"]
    assert oos["supersedes"] == old["id"]
    assert "supersedes" not in is_row
    assert oos["version"] == "selectivity_v1"
    assert oos["id"] == f"tema_cross.spot.m1.oos.selectivity_v1.{oos['date']}"


def test_run_m1_supersedes_requires_version(tmp_path, monkeypatch, capsys):
    from agents import loop_controller as lc

    gpath = tmp_path / "g.json"
    save_graph(empty_graph(updated="2026-08-24"), gpath)
    monkeypatch.setattr(lc, "GRAPH_PATH", gpath)
    monkeypatch.setattr(lc, "EXPERIMENTS_ROOT", tmp_path / "experiments")
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("must not spawn before --version check")

    monkeypatch.setattr(lc, "run_subprocess", boom)
    assert main([
        "run-m1", "--strategy", "tema_cross",
        "--supersedes", "tema_cross.spot.m5.2026-06-12",
    ]) == 1
    assert called["n"] == 0
    assert "--supersedes requires --version" in capsys.readouterr().err


def test_run_m1_dest_includes_version(tmp_path, monkeypatch):
    from agents import loop_controller as lc
    from datetime import date

    gpath = tmp_path / "g.json"
    save_graph(empty_graph(updated="2026-08-24"), gpath)
    monkeypatch.setattr(lc, "GRAPH_PATH", gpath)
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr(lc, "EXPERIMENTS_ROOT", exp_root)
    m1 = json.loads(Path("agents/fixtures/m1_sample.json").read_text())

    def fake_run(argv, timeout):
        json_path = Path(argv[argv.index("--json") + 1])
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(m1))
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(lc, "run_subprocess", fake_run)
    assert main([
        "run-m1", "--strategy", "tema_cross", "--registry", "spot",
        "--windows", "is,oos", "--version", "selectivity_v1",
        "--params", '{"mr_entry_z": 2.5}',
    ]) == 0
    dest = exp_root / f"{date.today().isoformat()}-tema_cross-spot-long-selectivity_v1-is+oos-m1"
    assert (dest / "m1.json").is_file()
    g = load_graph(gpath)
    assert all(e["version"] == "selectivity_v1" for e in g["entries"])


def test_run_m1_dest_includes_windows(tmp_path, monkeypatch):
    from agents import loop_controller as lc
    from datetime import date
    from argparse import Namespace

    monkeypatch.setattr(lc, "EXPERIMENTS_ROOT", tmp_path / "experiments")
    a = Namespace(
        strategy="regime_adaptive_htf", registry="spot", direction="long",
        version="selectivity_v1", windows="2023,2024,2025H1",
    )
    b = Namespace(
        strategy="regime_adaptive_htf", registry="spot", direction="long",
        version="selectivity_v1", windows="is,oos",
    )
    da = lc._run_m1_dest(a)
    db = lc._run_m1_dest(b)
    assert da != db
    assert da.name == (
        f"{date.today().isoformat()}-regime_adaptive_htf-spot-long-"
        "selectivity_v1-2023+2024+2025H1-m1"
    )


def test_next_prints_json_stop(capsys):
    assert main(["next"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "stop"
    assert "Do not un-stub" in payload["reason"]
