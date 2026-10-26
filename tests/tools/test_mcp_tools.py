import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "mcp"))

import hub_tools as t  # noqa: E402


class StubClient:
    """Records calls and answers from a path -> body map."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.responses.get(path, {})


def test_simple_wrappers_hit_expected_endpoints():
    c = StubClient()
    t.capture_status(c)
    t.capture_stop(c)
    t.setup_status(c)
    t.rescue_records(c)
    assert [(m, p) for m, p, _ in c.calls] == [
        ("GET", "/api/capture/status"),
        ("POST", "/api/capture/stop"),
        ("GET", "/api/setup/status"),
        ("GET", "/api/rescue/records"),
    ]


def test_capture_start_sends_region_and_debug():
    c = StubClient()
    t.capture_start(c, "asia", True)
    assert c.calls[0] == ("POST", "/api/capture/start", {"json": {"region": "asia", "debug": True}})


def test_log_tail_clamps_n():
    c = StubClient()
    t.capture_log_tail(c, 9999)
    t.capture_log_tail(c, 0)
    assert c.calls[0][2]["params"] == {"n": 500}
    assert c.calls[1][2]["params"] == {"n": 1}


def test_latest_snapshot_summarises():
    frags = [
        {"slot_name": "A", "set_name": "S1", "rarity": "R", "equipped_to": 1},
        {"slot_name": "A", "set_name": "S2", "rarity": "R", "equipped_to": None},
        {"slot_name": "B", "set_name": "S1", "rarity": "SR", "equipped_to": None},
    ]
    c = StubClient({"/api/status": {"data_loaded": True, "fragments": 3}, "/api/fragments": frags})
    out = t.latest_snapshot(c, limit=2)
    assert out["summary"]["total"] == 3
    assert out["summary"]["by_slot"] == {"A": 2, "B": 1}
    assert out["summary"]["by_set"] == {"S1": 2, "S2": 1}
    assert out["summary"]["equipped"] == 1
    assert len(out["fragments"]) == 2


def test_latest_snapshot_without_data_skips_fragments():
    c = StubClient({"/api/status": {"data_loaded": False}})
    out = t.latest_snapshot(c)
    assert out["summary"] is None and out["fragments"] == []
    assert [p for _, p, _ in c.calls] == ["/api/status"]


def test_latest_snapshot_passes_through_errors():
    c = StubClient({"/api/status": {"error": "Cannot reach sidecar"}})
    assert t.latest_snapshot(c)["summary"] is None


def test_replay_capture_parses_report():
    seen = {}

    def runner(cmd, **kwargs):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="Replaying x\nTotal events: 4\nReport -> C:/r/report.md\n", stderr="")

    out = t.replay_capture("cap.jsonl", runner=runner)
    assert out["ok"] and out["report"] == "C:/r/report.md"
    assert seen["cmd"][-1] == "cap.jsonl" and seen["cmd"][1].endswith("replay_capture.py")
    assert "Total events: 4" in out["summary"]


def test_replay_capture_failure_and_timeout():
    fail = lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="boom")
    out = t.replay_capture(runner=fail)
    assert not out["ok"] and out["stderr"] == "boom" and out["report"] is None

    def hang(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    assert not t.replay_capture(runner=hang)["ok"]


def test_client_reports_unreachable_sidecar():
    out = t.HubClient("http://127.0.0.1:1", "dev").request("GET", "/api/status")
    assert "error" in out
