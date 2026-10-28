"""
Pull tracker: the addon pairs `gacha/history` pages with their banner, keeps `gacha/get_list` pity, saves `gacha/run` pulls live, and merges history across sessions.

`gacha/get_list`, `gacha/history`, `gacha/run` and the record shape come from real captures (account ids scrubbed).
"""

import json
from types import SimpleNamespace

import pytest

from api.capture.addon import Addon, _rescue_record_key


def _flow(payload, from_client=False):
    msg = SimpleNamespace(from_client=from_client, is_text=True, text=json.dumps(payload), content=b"")
    return SimpleNamespace(request=SimpleNamespace(pretty_host="h", host="h"), websocket=SimpleNamespace(messages=[msg]))


def _record(rid, gacha_id="gacha_pickup_combatant_30115", reward=(20013, 20012, 1057), create_at=1787145526):
    return {
        "id": str(rid),
        "user_id": "300000000001",
        "gacha_id": gacha_id,
        "count": len(reward),
        "reward": json.dumps(list(reward)),
        "prism": json.dumps([0] * len(reward)),
        "createAt": str(create_at),
    }


PITY_REPLY = {
    "res": "ok",
    "gacha_pity_entity_list": [
        {"user_id": "300000000001", "res_id": "gacha_pity_general", "pity_ssr_count": 2, "pity_sr_count": 7, "mileage": 476, "updateAt": "1792606716"},
        {"user_id": "300000000001", "res_id": "gacha_pity_pickup_combatant", "pity_ssr_count": 6, "pity_sr_count": 7, "mileage": 1094, "updateAt": "1792621196"},
    ],
    "qid": 33,
}


def _ask(addon, qid, cmd, inner, **params):
    addon.websocket_message(_flow([{"cmd": cmd, "qid": qid, "params": {"cmd": inner, **params}}], from_client=True))


def _reply(addon, payload):
    addon.websocket_message(_flow([payload]))


def _load(tmp_path):
    files = sorted(tmp_path.glob("rescue_records_*.json"))
    assert files, "no rescue file written"
    return json.loads(files[-1].read_text(encoding="utf-8"))


@pytest.fixture
def addon(tmp_path):
    saved = []
    a = Addon(tmp_path, on_saved=saved.append)
    a.saved_kinds = saved
    return a


def test_record_key_uses_the_record_id_when_there_is_one():
    a = _record(1, reward=(1, 2))
    b = _record(1, reward=(3, 4), create_at=5)
    assert _rescue_record_key(a) == _rescue_record_key(b)
    assert _rescue_record_key(_record(2)) != _rescue_record_key(a)


def test_record_key_falls_back_to_content_without_an_id():
    a = _record(1)
    del a["id"]
    b = dict(a)
    assert _rescue_record_key(a) == _rescue_record_key(b)


def test_history_page_is_tagged_with_the_requested_pool(addon, tmp_path):
    _ask(addon, 7, "gacha", "history", id="gacha_pickup_partner_5001", last_db_id=0)
    rec = _record(10)
    del rec["gacha_id"]
    _reply(addon, {"res": "ok", "qid": 7, "gacha_history_list": [rec]})
    doc = _load(tmp_path)
    assert doc["records"][0]["gacha_id"] == "gacha_pickup_partner_5001"
    assert "gacha_pickup_partner_5001" in doc["pool_fetches"]
    assert "rescue" in addon.saved_kinds


def test_history_page_keeps_the_gacha_id_the_record_already_has(addon, tmp_path):
    _ask(addon, 7, "gacha", "history", id="gacha_pickup_partner_5001", last_db_id=0)
    _reply(addon, {"res": "ok", "qid": 7, "gacha_history_list": [_record(10)]})
    doc = _load(tmp_path)
    assert doc["records"][0]["gacha_id"] == "gacha_pickup_combatant_30115"
    assert "gacha_pickup_combatant_30115" in doc["pool_fetches"]


def test_history_without_a_request_is_still_saved(addon, tmp_path):
    _reply(addon, {"res": "ok", "qid": 99, "gacha_history_list": [_record(10)]})
    assert len(_load(tmp_path)["records"]) == 1


def test_history_merges_across_pages_and_sessions_without_dropping_old_records(tmp_path):
    first = Addon(tmp_path)
    _reply(first, {"res": "ok", "qid": 1, "gacha_history_list": [_record(1), _record(2)]})
    second = Addon(tmp_path)
    _reply(second, {"res": "ok", "qid": 1, "gacha_history_list": [_record(2), _record(3)]})
    ids = sorted(r["id"] for r in _load(tmp_path)["records"])
    assert ids == ["1", "2", "3"]


def test_get_list_stores_pity_per_pity_group(addon, tmp_path):
    _ask(addon, 33, "gacha", "get_list")
    _reply(addon, PITY_REPLY)
    doc = _load(tmp_path)
    assert doc["pity"]["gacha_pity_pickup_combatant"]["pity_ssr_count"] == 6
    assert doc["pity"]["gacha_pity_general"]["pity_sr_count"] == 7
    assert "rescue" in addon.saved_kinds


def test_get_list_keeps_existing_records(addon, tmp_path):
    _reply(addon, {"res": "ok", "qid": 1, "gacha_history_list": [_record(1)]})
    _ask(addon, 33, "gacha", "get_list")
    _reply(addon, PITY_REPLY)
    doc = _load(tmp_path)
    assert len(doc["records"]) == 1
    assert doc["pity"]


def test_get_list_reply_without_its_request_is_ignored(addon, tmp_path):
    _reply(addon, PITY_REPLY)
    assert not list(tmp_path.glob("rescue_records_*.json"))


def test_each_save_records_when_the_session_started(addon, tmp_path):
    _reply(addon, {"res": "ok", "qid": 1, "gacha_history_list": [_record(1)]})
    doc = _load(tmp_path)
    assert doc["session_start"] == addon.session_start
    assert doc["pool_fetches"]["gacha_pickup_combatant_30115"] >= doc["session_start"]


def test_manager_pushes_a_snapshot_updated_event_for_rescue_saves(tmp_path):
    from api.capture.manager import CaptureManager

    events = []
    mgr = CaptureManager(output_folder=tmp_path, log_callback=lambda *a, **k: None, event_callback=events.append)
    mgr._on_saved("rescue")
    mgr._on_saved("battle")
    assert [(e["type"], e["kind"]) for e in events] == [("snapshot_updated", "rescue")]


# A trimmed `gacha/run` reply from a real 10-pull. The pity entity is the state after the pull.
RUN_REPLY = {
    "res": "ok",
    "result": True,
    "list": [
        {"index": 1, "res_id": 20013, "is_new": 0, "is_prism": 0},
        {"index": 0, "res_id": 20012, "is_new": 0, "is_prism": 0},
        {"index": 2, "res_id": 1021, "is_new": 0, "is_prism": 1},
    ],
    "gacha_pity_entity": {"user_id": "300000000001", "res_id": "gacha_pity_card_factor", "pity_ssr_count": 14, "pity_sr_count": 0, "mileage": 736,
                          "updateAt": "1792620656"},
    "service_server_time": 1793136810,
    "qid": 44,
}


def _pull(addon, reply=RUN_REPLY, pool="gacha_card_factor"):
    _ask(addon, 44, "gacha", "run", id=pool, count=len(reply["list"]))
    _reply(addon, reply)


def test_a_pull_is_saved_as_it_happens(addon, tmp_path):
    _pull(addon)
    doc = _load(tmp_path)
    [record] = doc["records"]
    assert record["gacha_id"] == "gacha_card_factor"
    assert json.loads(record["reward"]) == [20012, 20013, 1021]
    assert json.loads(record["prism"]) == [0, 0, 1]
    assert record["createAt"] == "1793136810"
    assert record["live"] is True
    assert doc["pity"]["gacha_pity_card_factor"]["pity_ssr_count"] == 14
    assert "rescue" in addon.saved_kinds


def test_a_pull_does_not_mark_its_banner_history_as_refreshed(addon, tmp_path):
    # Pulls made on another device are only in the history, so a live pull must not hide that the history is out of date.
    _pull(addon)
    assert "gacha_card_factor" not in _load(tmp_path).get("pool_fetches", {})


def test_a_pull_reply_without_its_request_is_ignored(addon, tmp_path):
    _reply(addon, RUN_REPLY)
    assert not list(tmp_path.glob("rescue_records_*.json"))


def test_the_history_entry_for_a_live_pull_replaces_it(addon, tmp_path):
    _pull(addon)
    _ask(addon, 7, "gacha", "history", id="gacha_card_factor", last_db_id=0)
    _reply(addon, {"res": "ok", "qid": 7, "next_page_exists": False, "gacha_history_list": [
        _record(900, gacha_id="gacha_card_factor", reward=(20012, 20013, 1021), create_at=1793136811)]})
    [record] = _load(tmp_path)["records"]
    assert record["id"] == "900"
    assert "live" not in record


def test_a_history_entry_replaces_only_one_of_two_identical_pulls(addon, tmp_path):
    _pull(addon)
    _pull(addon)
    _ask(addon, 7, "gacha", "history", id="gacha_card_factor", last_db_id=0)
    _reply(addon, {"res": "ok", "qid": 7, "next_page_exists": True, "gacha_history_list": [
        _record(900, gacha_id="gacha_card_factor", reward=(20012, 20013, 1021), create_at=1793136811)]})
    assert sorted(bool(r.get("live")) for r in _load(tmp_path)["records"]) == [False, True]


def test_a_different_history_entry_keeps_the_live_pull(addon, tmp_path):
    _pull(addon)
    _reply(addon, {"res": "ok", "qid": 7, "gacha_history_list": [
        _record(900, gacha_id="gacha_card_factor", reward=(20012, 20013, 1021), create_at=1793130000)]})
    assert len(_load(tmp_path)["records"]) == 2


def test_a_history_page_says_whether_another_page_follows(addon, tmp_path):
    _ask(addon, 7, "gacha", "history", id="gacha_card_factor", last_db_id=0)
    _reply(addon, {"res": "ok", "qid": 7, "next_page_exists": True, "gacha_history_list": [_record(10)]})
    first = _load(tmp_path)["last_history_page"]
    assert first["pool"] == "gacha_card_factor"
    assert first["has_more"] is True
    _ask(addon, 8, "gacha", "history", id="gacha_card_factor", last_db_id=10)
    _reply(addon, {"res": "ok", "qid": 8, "next_page_exists": False, "gacha_history_list": [_record(9)]})
    last = _load(tmp_path)["last_history_page"]
    assert last["has_more"] is False
    assert last["seq"] == first["seq"] + 1
    assert len(_load(tmp_path)["records"]) == 2
