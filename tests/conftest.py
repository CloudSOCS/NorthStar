import pytest


@pytest.fixture(autouse=True)
def isolate_live_halt_file(monkeypatch, tmp_path):
    """Never read the human ~/.poly/live_halt.json during tests."""
    monkeypatch.setenv("NORTHSTAR_LIVE_HALT", str(tmp_path / "live_halt.json"))
