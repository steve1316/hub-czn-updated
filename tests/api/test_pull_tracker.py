"""
Pull tracker: the addon pairs `gacha/history` pages with their banner, keeps `gacha/get_list` pity, and merges history across sessions.

`gacha/get_list` and the record shape come from real captures (account ids scrubbed). The `gacha/history` request shape is from the project plan and
has not been seen in a capture yet.
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
