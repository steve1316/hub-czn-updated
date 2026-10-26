"""
Live capture: the game batches replies into JSON lists after login, and the addon has to keep reading them.

Frames here are hand-built in the shapes documented by the Vribbels pipeline notes. A real play session still has to confirm them.
"""

import json
import time
from types import SimpleNamespace

import pytest

from api.capture.addon import Addon
from api.capture.dispatch import CommandDispatch, RequestTracker, unwrap_frame


def _piece(pid, char=0, level=0):
    return {"id": pid, "res_id": 10101001, "char_res_id": char, "level": level, "stat_list": []}


def _flow(payload, from_client=False):
    msg = SimpleNamespace(from_client=from_client, is_text=True, text=json.dumps(payload), content=b"")
    return SimpleNamespace(request=SimpleNamespace(pretty_host="h", host="h"), websocket=SimpleNamespace(messages=[msg]))


def _client(addon, entries):
    addon.websocket_message(_flow(entries, from_client=True))


def _server(addon, payload):
    addon.websocket_message(_flow(payload))


def _login(addon):
    """Feed a login-shaped inventory and roster so deltas have something to fold into."""
    _server(addon, {"res": "ok", "qid": 2, "piece_items": [_piece(1), _piece(2, char=1009), _piece(3)], "items": [{"res_id": 3000005, "amount": 10}]})
    _server(
        addon,
        {
            "res": "ok",
            "qid": 3,
            "user": {"id": "u1", "lv": 50, "last_login_tm": 100},
            "characters": [{"res_id": 1009, "exp": 1}, {"res_id": 1010, "exp": 2}],
            "currencies": {"2000001": {"res_id": 2000001, "amount": 500}},
        },
    )


@pytest.fixture
def addon(tmp_path):
    saved = []
    a = Addon(tmp_path, on_saved=saved.append)
    a.saved_kinds = saved
    return a


def _ids(addon):
    return [p["id"] for p in addon.inventory_data["piece_items"]]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Dispatch helpers


def test_unwrap_frame_handles_dict_list_and_junk():
    assert unwrap_frame({"a": 1}) == [{"a": 1}]
    assert unwrap_frame([{"a": 1}, 5, "x", {"b": 2}]) == [{"a": 1}, {"b": 2}]
    assert unwrap_frame("nope") == []
    assert unwrap_frame(None) == []


def test_tracker_pairs_by_qid_and_names_the_inner_command():
    t = RequestTracker()
    t.note_frame([{"cmd": "item", "qid": 5, "params": {"cmd": "unequip_piece", "x": 1}}, {"cmd": "town", "qid": 6}])
    assert t.get(5).name == "item/unequip_piece"
    assert t.get(5).params["x"] == 1
    assert t.get(6).name == "town"
    assert t.get(99) is None


def test_helo_clears_pending_requests():
    t = RequestTracker()
    t.note_frame([{"cmd": "item", "qid": 5, "params": {"cmd": "disassemble_piece"}}])
    t.note_frame([{"cmd": "helo", "qid": 1}])
    assert t.get(5) is None
    assert len(t) == 0


def test_dispatch_calls_exact_and_family_handlers():
    seen = []
    d = CommandDispatch()
    d.register("gacha/run", lambda payload, req: seen.append(("run", req.name)))
    d.register("gacha", lambda payload, req: seen.append(("family", req.name)))
    t = RequestTracker()
    t.note_frame([{"cmd": "gacha", "qid": 7, "params": {"cmd": "run"}}])
    assert d.dispatch(t.get(7), {"qid": 7}) == 2
    assert seen == [("run", "gacha/run"), ("family", "gacha/run")]
    assert d.dispatch(None, {"qid": 8}) == 0


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Frames


def test_single_dict_frame_still_works(addon):
    _login(addon)
    assert _ids(addon) == [1, 2, 3]
    assert addon.character_data["user"]["id"] == "u1"
    assert addon.saved_path is not None


def test_list_frame_is_unwrapped(addon):
    _login(addon)
    _server(addon, [{"res": "ok", "qid": 9, "piece": _piece(1, char=1009, level=1)}, {"res": "ok", "qid": 10, "user": {"id": "u1", "lv": 51, "last_login_tm": 100}}])
    assert addon.inventory_data["piece_items"][0]["level"] == 1
    assert addon.character_data["user"]["lv"] == 51


def test_list_frame_saves_once_per_frame(addon):
    _login(addon)
    addon.saved_kinds.clear()
    _server(addon, [{"res": "ok", "qid": 9, "piece": _piece(1, level=1)}, {"res": "ok", "qid": 10, "piece": _piece(3, level=2)}])
    assert addon.saved_kinds == ["fragments"]


def test_non_ok_reply_in_list_is_skipped(addon):
    _login(addon)
    _server(addon, [{"res": "err", "qid": 9, "piece": _piece(1, level=9)}])
    assert addon.inventory_data["piece_items"][0]["level"] == 0


def test_client_list_is_tracked_not_applied(addon):
    _login(addon)
    _client(addon, [{"cmd": "item", "qid": 20, "params": {"cmd": "disassemble_piece", "item_db_ids": [1]}}])
    assert _ids(addon) == [1, 2, 3]
    assert addon.tracker.get(20).name == "item/disassemble_piece"


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Deltas


def test_create_appends_new_pieces(addon):
    _login(addon)
    _server(addon, [{"res": "ok", "qid": 11, "pieces": [_piece(4), _piece(1)], "item_result": {}}])
    assert _ids(addon) == [1, 2, 3, 4]


def test_disassemble_removes_pieces_named_in_the_request(addon):
    _login(addon)
    _client(addon, [{"cmd": "item", "qid": 20, "params": {"cmd": "disassemble_piece", "item_db_ids": [1, 3]}}])
    _server(addon, [{"res": "ok", "qid": 20, "item_result": {}}])
    assert _ids(addon) == [2]


def test_disassemble_not_applied_after_helo_reset(addon):
    _login(addon)
    _client(addon, [{"cmd": "item", "qid": 20, "params": {"cmd": "disassemble_piece", "item_db_ids": [1]}}])
    _client(addon, [{"cmd": "helo", "qid": 1}])
    _server(addon, [{"res": "ok", "qid": 20, "item_result": {}}])
    assert _ids(addon) == [1, 2, 3]


def test_equip_swap_replaces_both_pieces(addon):
    _login(addon)
    _server(addon, [{"res": "ok", "qid": 12, "piece": _piece(1, char=1010), "equippedPiece": _piece(2, char=0)}])
    by_id = {p["id"]: p for p in addon.inventory_data["piece_items"]}
    assert by_id[1]["char_res_id"] == 1010
    assert by_id[2]["char_res_id"] == 0


def test_unequip_all_replaces_in_place_instead_of_appending(addon):
    _login(addon)
    _client(addon, [{"cmd": "item", "qid": 21, "params": {"cmd": "unequip_piece", "item_db_ids": [2], "char_res_id": "1009"}}])
    _server(addon, [{"res": "ok", "qid": 21, "pieces": [_piece(2, char=0)]}])
    assert _ids(addon) == [1, 2, 3]
    assert addon.inventory_data["piece_items"][1]["char_res_id"] == 0


def test_reward_pieces_are_added(addon):
    _login(addon)
    reward = {"res": "ok", "qid": 13, "return_info": {"result_reward_drop_item": {"pieces": {"9": {"diff": 1, "doc": _piece(9)}}}}}
    _server(addon, [reward])
    assert 9 in _ids(addon)


def test_characters_delta_is_merged_not_replaced(addon):
    _login(addon)
    _server(addon, [{"res": "ok", "qid": 14, "characters": [{"res_id": 1009, "exp": 99}]}])
    chars = {c["res_id"]: c for c in addon.character_data["characters"]}
    assert chars[1009]["exp"] == 99
    assert chars[1010]["exp"] == 2
    assert addon.character_data["user"]["id"] == "u1"
    assert "currencies" in addon.character_data


def test_full_characters_payload_replaces(addon):
    _login(addon)
    roster = [{"res_id": 1009, "exp": 5}, {"res_id": 1010, "exp": 6}, {"res_id": 1011, "exp": 7}]
    _server(addon, {"res": "ok", "qid": 15, "user": {"id": "u1", "last_login_tm": 100}, "characters": roster})
    assert len(addon.character_data["characters"]) == 3


def test_user_alone_patches_without_dropping_the_roster(addon):
    _login(addon)
    _server(addon, [{"res": "ok", "qid": 16, "user": {"id": "u1", "lv": 60, "last_login_tm": 100}}])
    assert addon.character_data["user"]["lv"] == 60
    assert len(addon.character_data["characters"]) == 2


def test_item_and_currency_totals_are_written_not_added(addon):
    _login(addon)
    frame = {
        "res": "ok",
        "qid": 17,
        "add_result": {
            "items": {"3000005": {"doc": {"res_id": 3000005, "amount": 15}, "diff": 5}, "3000009": {"doc": {"res_id": 3000009, "amount": 1}, "diff": 1}},
            "currency": {"2000001": {"doc": {"res_id": 2000001, "amount": 450}, "diff": -50}},
        },
    }
    _server(addon, [frame])
    _server(addon, [frame])
    items = {i["res_id"]: i["amount"] for i in addon.inventory_data["items"]}
    assert items == {3000005: 15, 3000009: 1}
    assert addon.character_data["currencies"]["2000001"]["amount"] == 450


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Snapshot rotation


def test_reconnect_does_not_rotate_but_new_last_login_does(addon):
    _login(addon)
    first = addon.saved_path
    _client(addon, [{"cmd": "helo", "qid": 1}])
    _server(addon, {"res": "ok", "qid": 2, "user": {"id": "u1", "last_login_tm": 100}})
    assert addon.saved_path == first

    _server(addon, {"res": "ok", "qid": 3, "user": {"id": "u1", "last_login_tm": 200}})
    assert addon.saved_path != first


def test_rotation_writes_a_new_file_on_next_save(addon):
    _login(addon)
    first = addon.saved_path
    _server(addon, {"res": "ok", "qid": 3, "user": {"id": "u1", "last_login_tm": 200}})
    time.sleep(1.1)
    _server(addon, {"res": "ok", "qid": 4, "piece": _piece(1, level=3)})
    assert addon.saved_path is not None and addon.saved_path != first
    assert first.exists() and addon.saved_path.exists()


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# UI event


def test_save_reports_a_fragments_event(tmp_path):
    events = []
    a = Addon(tmp_path, on_saved=events.append)
    _login(a)
    assert "fragments" in events
