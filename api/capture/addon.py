"""
mitmproxy Addon for intercepting CZN game WebSocket traffic.
Extracts Memory Fragment inventory and character data from game API responses.

The live-delta handling (list frames, qid pairing, piece / character / totals folding, relaunch rotation) is ported in part from
Vribbels-CZN-Optimizer, MIT, (c) 2025 Vorbroker, 2026 Ikkoru.
"""

import json
import gzip
import time
import zlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from game_data import CHARACTERS, SETS
from game_data.constants import EQUIPMENT_SLOTS

from .constants import SERVERS
from .dispatch import CommandDispatch, PendingRequest, RequestTracker, unwrap_frame

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

# Lookup tables for the live monitoring log lines. These used to be injected into a generated
# script; now the addon is a real module and reads them straight from game_data.
CHAR_NAMES = {rid: c["name"] for rid, c in CHARACTERS.items() if c is not None}
SET_NAMES = {sid: s["name"] for sid, s in SETS.items()}
SLOT_NAMES = {k: v.split(" ", 1)[1] if " " in v else v for k, v in EQUIPMENT_SLOTS.items()}

# Which region each game host belongs to, so a capture can record the server it actually talked to.
HOST_TO_REGION = {host: cfg.region_id for cfg in SERVERS.values() for host in cfg.hosts}

# Zstandard frame header, used to spot compressed WebSocket payloads.
ZSTD_MAGIC = bytes([0x28, 0xB5, 0x2F, 0xFD])

# Every key the server has been seen to use for the pull history.
RESCUE_KEYS = (
    "gacha_history_list",
    "gacha_records", "rescue_records", "gacha_record_list",
    "rescue_record_list", "rescue_history", "gacha_history",
    "pull_records", "pickup_records",
)

# Client commands whose reply carries no detail, so the request is what says which pieces changed.
CMD_DISASSEMBLE = "item/disassemble_piece"
CMD_UNEQUIP = "item/unequip_piece"

# Pull tracker commands. History pages name their banner in the request, and the pity list has its own reply key.
CMD_GACHA_HISTORY = "gacha/history"
CMD_GACHA_LIST = "gacha/get_list"
PITY_KEY = "gacha_pity_entity_list"

# Reply keys that state what a holding now is, with `doc.amount` as the total.
TOTALS_KEYS = ("add_result", "item_result", "dec_result")


def _upsert(rows: list, row, key="id"):
    """
    Replace the row with the same key in place, or append it.

    Args:
        rows: The list to update.
        row: The new row.
        key: A dict key name, or a function that returns the identity of a row.

    Returns:
        The row that was replaced, or None when `row` was appended.
    """
    ident = key if callable(key) else (lambda r: r.get(key))
    target = ident(row)
    for i, existing in enumerate(rows):
        if ident(existing) == target:
            rows[i] = row
            return existing
    rows.append(row)
    return None


def _docs(rows) -> list:
    """
    Pull the `doc` out of each `{diff, doc}` entry in a dict.

    Args:
        rows: A dict of entries, or anything else.

    Returns:
        The dict docs found, or an empty list when `rows` is not a dict.
    """
    if not isinstance(rows, dict):
        return []
    return [e["doc"] for e in rows.values() if isinstance(e, dict) and isinstance(e.get("doc"), dict)]


def _rescue_record_key(record: dict) -> str:
    """Stable dedup key. The server record id wins when there is one, otherwise the semantic fields are used."""
    if record.get("id") not in (None, ""):
        return f"id|{record['id']}"
    gacha_id = str(record.get("gacha_id", ""))
    try:
        create_at = int(record.get("createAt", 0))
    except (ValueError, TypeError):
        create_at = 0
    reward_raw = record.get("reward", [])
    if isinstance(reward_raw, str):
        try:
            reward_raw = json.loads(reward_raw)
        except Exception:
            reward_raw = []
    reward = sorted(int(r) for r in (reward_raw or []) if r is not None)
    return f"{gacha_id}|{create_at}|{reward}"


class Addon:
    """mitmproxy addon that intercepts WebSocket messages and extracts game data."""

    def __init__(
        self,
        output_dir: Path,
        dict_path: Optional[Path] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        debug_mode: bool = False,
        on_saved: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the capture addon.

        Args:
            output_dir: Directory to save captured JSON files
            dict_path: Optional path to zstd dictionary file
            log_callback: Optional callback for logging messages (defaults to print)
            debug_mode: If True, log all WebSocket messages to a .jsonl file
            on_saved: Called with "fragments", "rescue" or "battle" after a snapshot is written,
                so the UI can reload it
        """
        self.output_dir = output_dir
        self.log_callback = log_callback or (lambda msg: print(msg, flush=True))
        self.on_saved = on_saved or (lambda kind: None)
        self.inventory_data = None
        self.character_data = None
        self.saved_path = None
        self.rescue_path = None
        self.battle_path = None
        self.battle_data: dict = {}
        self.zstd_dict = None
        self.zstd_dctx = None
        # Hosts the game actually connected to, used to work out the region.
        self.seen_hosts: set = set()
        # Client requests by qid, and the handlers that run when their reply arrives.
        self.tracker = RequestTracker()
        self.dispatch = CommandDispatch()
        self.dispatch.register(CMD_DISASSEMBLE, self._on_disassemble)
        self.dispatch.register(CMD_UNEQUIP, self._on_unequip)
        self.dispatch.register(CMD_GACHA_HISTORY, self._on_gacha_history)
        self.dispatch.register(CMD_GACHA_LIST, self._on_gacha_list)
        # When this capture started, so the page can tell which banners were refreshed during it.
        self.session_start = int(time.time())
        # Set by a delta so the snapshot is written once at the end of the frame.
        self._save_pending = False
        # The `last_login_tm` of the account's current game launch. A change means a new launch.
        self.login_stamp = None
        # Set once the "no inventory yet" hint has been logged, so it shows only once.
        self._warned_no_inventory = False

        # Debug logging
        self.debug_file = None
        if debug_mode:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_path = self.output_dir / f"websocket_debug_{ts}.jsonl"
            self.debug_file = open(debug_path, "w", encoding="utf-8")
            self.log_callback(f"Debug logging to: {debug_path.name}")

        # Load zstd dictionary if available
        if dict_path and dict_path.exists() and HAS_ZSTD:
            try:
                with open(dict_path, 'rb') as f:
                    dict_data = f.read()
                self.zstd_dict = zstd.ZstdCompressionDict(dict_data)
                self.zstd_dctx = zstd.ZstdDecompressor(dict_data=self.zstd_dict)
            except Exception as e:
                self.log_callback(f"Warning: Failed to load zstd dictionary: {e}")

    def _write_debug(self, entry: dict):
        """Append one line to the debug JSONL. Does nothing when debug mode is off."""
        if not self.debug_file:
            return
        self.debug_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.debug_file.flush()

    def _detect_region(self) -> Optional[str]:
        """
        Work out which server this capture came from, using the hosts the game connected to.

        The payload carries no region of its own. This used to look for a `world_id` field that the
        server never sends, so it always returned None and the region was never detected.

        Returns:
            "global" or "asia", or None if no known game host was seen.
        """
        for host in self.seen_hosts:
            region = HOST_TO_REGION.get(host)
            if region:
                return region
        return None

    def _try_decode_binary(self, raw_bytes):
        """
        Try to decode binary data - may be compressed or plain JSON.
        Returns decoded string or None if unable to decode.
        """
        # Try plain UTF-8 first
        try:
            return raw_bytes.decode('utf-8')
        except:
            pass

        # Check for Zstandard magic number (0x28 0xB5 0x2F 0xFD)
        is_zstd = len(raw_bytes) >= 4 and raw_bytes[:4] == ZSTD_MAGIC

        if is_zstd:
            if HAS_ZSTD:
                # Try with dictionary first (required for CZN game data)
                if self.zstd_dctx:
                    try:
                        decompressed = self.zstd_dctx.decompress(raw_bytes)
                        return decompressed.decode('utf-8')
                    except:
                        pass

                # Try without dictionary as fallback
                try:
                    dctx = zstd.ZstdDecompressor()
                    decompressed = dctx.decompress(raw_bytes)
                    return decompressed.decode('utf-8')
                except:
                    pass
            else:
                self.log_callback("ERROR: zstandard module not installed!")

        # Try zstd anyway (in case magic check failed)
        if HAS_ZSTD and not is_zstd:
            # Try with dictionary first
            if self.zstd_dctx:
                try:
                    decompressed = self.zstd_dctx.decompress(raw_bytes)
                    return decompressed.decode('utf-8')
                except:
                    pass
            # Try without dictionary
            try:
                dctx = zstd.ZstdDecompressor()
                decompressed = dctx.decompress(raw_bytes)
                return decompressed.decode('utf-8')
            except:
                pass

        # Try gzip decompression
        try:
            decompressed = gzip.decompress(raw_bytes)
            return decompressed.decode('utf-8')
        except:
            pass

        # Try zlib decompression (with and without header)
        for wbits in [15, -15, 31, 47]:
            try:
                decompressed = zlib.decompress(raw_bytes, wbits)
                return decompressed.decode('utf-8')
            except:
                pass

        return None

    def websocket_message(self, flow):
        """
        Handle WebSocket messages from both directions.
        Server frames feed the inventory/battle pipeline; client frames are
        only logged in debug mode.

        Args:
            flow: mitmproxy flow object containing WebSocket messages
        """
        # pretty_host prefers the Host header, which the game still sets to the real server even
        # though the hosts file sent the connection to us.
        host = getattr(flow.request, "pretty_host", None) or getattr(flow.request, "host", None)
        if host:
            self.seen_hosts.add(host)

        msg = flow.websocket.messages[-1]
        direction = "c2s" if msg.from_client else "s2c"

        try:
            # Handle both text and binary WebSocket frames
            if msg.is_text:
                content = msg.text
            else:
                content = self._try_decode_binary(msg.content)

            if content is None:
                # Could not decode (probably a different encoding for c2s).
                # Log a hex preview so we can diagnose without losing the frame.
                if self.debug_file:
                    raw = msg.content if not msg.is_text else b""
                    entry = {
                        "ts": datetime.now().isoformat(),
                        "dir": direction,
                        "decode": "failed",
                        "size": len(raw),
                        "hex_head": raw[:64].hex(),
                    }
                    self._write_debug(entry)
                return

            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                if self.debug_file:
                    entry = {
                        "ts": datetime.now().isoformat(),
                        "dir": direction,
                        "decode": "not_json",
                        "size": len(content),
                        "preview": content[:300],
                    }
                    self._write_debug(entry)
                return

            payloads = unwrap_frame(data)

            # Client frames only teach the tracker which command each qid is.
            if msg.from_client:
                self.tracker.note_frame(data)
                for payload in payloads:
                    self._debug_payload(payload, direction, len(content))
                return

            for payload in payloads:
                self._debug_payload(payload, direction, len(content))
                self._handle_server_payload(payload)

            if self._save_pending:
                self._save_pending = False
                self._save_data()

        except Exception as e:
            self.log_callback(f"Error: {e}")

    def _debug_payload(self, payload: dict, direction: str, size: int):
        """Log one decoded message to the debug JSONL before any filtering. Does nothing when debug mode is off."""
        if self.debug_file:
            self._write_debug({"ts": datetime.now().isoformat(), "dir": direction, "keys": list(payload.keys()), "size": size, "data": payload})

    def _hint_no_inventory(self, data: dict, request: PendingRequest | None):
        """
        Log once that a gear change was skipped because no login inventory has been captured yet.

        Args:
            data: One decoded reply object.
            request: The client request this reply answers, if it was seen.
        """
        if self._warned_no_inventory:
            return
        gear_request = request is not None and request.name in (CMD_UNEQUIP, CMD_DISASSEMBLE)
        if "piece" in data or "pieces" in data or gear_request or self._reward_pieces(data):
            self._warned_no_inventory = True
            self.log_callback("[LIVE] Gear change seen, but no inventory captured yet. Restart the game while capture is running.")

    def _mark_dirty(self):
        """Ask for the snapshot to be written at the end of the current frame."""
        self._save_pending = True

    def _handle_server_payload(self, data: dict):
        """
        Act on one server reply. A frame yields one of these, or several when the server answers a batch.

        Args:
            data: One decoded reply object.
        """
        if data.get("res") != "ok":
            return

        request = self.tracker.pop(data.get("qid"))
        self.dispatch.dispatch(request, data)
        unequip = request is not None and request.name == CMD_UNEQUIP

        # Live monitoring: "piece" is an upgrade / swap / equip, and "pieces" is a create (an unequip-all answers with it too, handled above).
        if self.inventory_data and "piece_items" in self.inventory_data:
            if "piece" in data:
                self._apply_piece_delta(data)
            elif "pieces" in data and not unequip:
                self._apply_pieces_create(data.get("pieces"))
            reward = self._reward_pieces(data)
            if reward:
                self._apply_pieces_create(reward)
        elif "piece_items" not in data:
            self._hint_no_inventory(data, request)

        # The 'info' structure (new API format)
        info = data.get("info")
        info = info if isinstance(info, dict) else {}
        item_info = info.get("item")
        if isinstance(item_info, dict) and "piece" in item_info:
            self.inventory_data = self.inventory_data or {}
            self.inventory_data["info_item_piece"] = item_info["piece"]
            self._mark_dirty()
        if "character" in info:
            self.character_data = self.character_data or {}
            self.character_data["info_character"] = info["character"]
            self._mark_dirty()

        # Capture inventory data (Memory Fragments)
        if "piece_items" in data:
            self.inventory_data = data
            self._mark_dirty()

        # Item and currency totals state what a holding now is.
        for key in TOTALS_KEYS:
            if isinstance(data.get(key), dict):
                self._apply_totals(data[key])

        # Character data. The login sends the full roster and later replies can send only the entries that changed.
        has_characters = "characters" in data and isinstance(data.get("characters"), list)
        has_user = "user" in data

        if has_user:
            self._check_for_relaunch(data["user"])

        if has_characters:
            self._merge_character_data(data)
            self._mark_dirty()
        elif has_user:
            # A user update with no roster is patched in so the roster survives.
            if self.character_data:
                self.character_data["user"] = data["user"]
            else:
                self.character_data = data
            self._mark_dirty()

        # Capture rescue/gacha records (pull history)
        for key in RESCUE_KEYS:
            if key in data:
                self._save_rescue_data(key, data[key])
                break

        # Capture battle data
        if "battle_info" in data:
            self._on_battle_info(data["battle_info"])
        if "return_info" in data:
            self._on_return_info(data["return_info"])
        if "snapshot" in data:
            self._on_snapshot(data["snapshot"])

    # ---- HTTP capture (debug only) ------------------------------------
    # The game appears to send commands via HTTP POST and only receives
    # push frames over WebSocket. These hooks log every HTTP request and
    # response to the same debug JSONL so request/response can be paired
    # by qid.

    def _log_http(self, flow, kind: str):
        if not self.debug_file:
            return
        try:
            if kind == "http_req":
                msg = flow.request
            else:
                msg = flow.response
            if msg is None:
                return
            raw = msg.raw_content or b""
            content = self._try_decode_binary(raw) if raw else ""
            entry = {
                "ts": datetime.now().isoformat(),
                "dir": kind,
                "method": getattr(flow.request, "method", None),
                "url": getattr(flow.request, "pretty_url", None),
                "size": len(raw),
            }
            if content is None:
                entry["decode"] = "failed"
                entry["hex_head"] = raw[:64].hex()
            else:
                try:
                    parsed = json.loads(content) if content else None
                    entry["data"] = parsed
                    if isinstance(parsed, dict):
                        entry["keys"] = list(parsed.keys())
                except json.JSONDecodeError:
                    entry["decode"] = "not_json"
                    entry["preview"] = content[:300]
            self._write_debug(entry)
        except Exception as e:
            self.log_callback(f"http debug log error: {e}")

    def request(self, flow):
        self._log_http(flow, "http_req")

    def response(self, flow):
        self._log_http(flow, "http_resp")

    def _save_data(self):
        """
        Save captured data to JSON file.
        Only saves when inventory data is available.
        Combines inventory and character data into single file.
        """
        if not self.inventory_data:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        if not self.saved_path:
            self.saved_path = self.output_dir / f"memory_fragments_{ts}.json"
            # A rotation inside the same second must not overwrite the previous launch's file.
            n = 1
            while self.saved_path.exists():
                n += 1
                self.saved_path = self.output_dir / f"memory_fragments_{ts}_{n}.json"

        save_data = {
            "capture_time": datetime.now().isoformat(),
            "inventory": self.inventory_data,
            "characters": self.character_data,
            "detected_region": self._detect_region(),
        }

        with open(self.saved_path, "w") as f:
            json.dump(save_data, f, indent=2)

        count = len(self.inventory_data.get("piece_items", []))
        char_count = len(self.character_data.get("characters", [])) if self.character_data else 0
        self.log_callback(
            f"Saved: {count} Memory Fragments, {char_count} characters -> {self.saved_path.name}"
        )
        self.on_saved("fragments")

    def _describe_piece(self, piece_data):
        """Build human-readable piece description like 'Line of Justice Denial (+3)'."""
        res_id = piece_data.get("res_id", 0)
        level = piece_data.get("level", 0)
        res_str = str(res_id)
        if len(res_str) >= 5:
            slot_num = int(res_str[2])
            set_id = int(res_str[4:])
            set_name = SET_NAMES.get(set_id, f"Set{set_id}")
            slot_name = SLOT_NAMES.get(slot_num, f"Slot{slot_num}")
            return f"{set_name} {slot_name} (+{level})"
        return f"Piece {piece_data.get('id', '?')} (+{level})"

    def _apply_piece_delta(self, data):
        """Apply a piece delta update to inventory and log the change."""
        piece_items = self.inventory_data.get("piece_items", [])
        new_piece = data["piece"]
        equipped_piece = data.get("equippedPiece")

        old_piece = _upsert(piece_items, new_piece)
        if equipped_piece:
            _upsert(piece_items, equipped_piece)

        self._mark_dirty()

        # Build log message
        desc = self._describe_piece(new_piece)
        char_id = new_piece.get("char_res_id", 0)
        char_name = CHAR_NAMES.get(char_id, f"Character {char_id}")

        if equipped_piece:
            eq_desc = self._describe_piece(equipped_piece)
            self.log_callback(f"[LIVE] Swapped gear on {char_name}: equipped {desc}, removed {eq_desc}")
        elif old_piece and old_piece.get("level", 0) != new_piece.get("level", 0):
            self.log_callback(f"[LIVE] Upgraded {desc}")
        elif char_id != 0:
            self.log_callback(f"[LIVE] Equipped {desc} to {char_name}")
        else:
            self.log_callback(f"[LIVE] Unequipped {desc}")

    def _on_disassemble(self, data: dict, request: PendingRequest):
        """
        Remove the pieces a `disassemble_piece` request named. The reply carries only proceeds, so the request is the only record of which pieces went.

        Args:
            data: The server reply.
            request: The paired client request.
        """
        ids = request.params.get("item_db_ids") or []
        if not (isinstance(ids, list) and ids and self.inventory_data and "piece_items" in self.inventory_data):
            return
        piece_items = self.inventory_data["piece_items"]
        target = set(ids)
        removed = [p for p in piece_items if p.get("id") in target]
        if not removed:
            return
        self.inventory_data["piece_items"] = [p for p in piece_items if p.get("id") not in target]
        self._mark_dirty()
        if len(removed) == 1:
            self.log_callback(f"[LIVE] Deleted {self._describe_piece(removed[0])}")
        else:
            self.log_callback(f"[LIVE] Deleted {len(removed)} pieces")

    def _on_unequip(self, data: dict, request: PendingRequest):
        """
        Apply an "Unequip All" reply. Its `pieces` list shares a shape with a create, so the request is what tells them apart.

        Args:
            data: The server reply.
            request: The paired client request.
        """
        pieces = data.get("pieces")
        if not (isinstance(pieces, list) and self.inventory_data and "piece_items" in self.inventory_data):
            return
        try:
            char_id = int(request.params.get("char_res_id") or 0)
        except (TypeError, ValueError):
            char_id = 0
        piece_items = self.inventory_data["piece_items"]
        updated = 0
        for new_piece in pieces:
            if not isinstance(new_piece, dict):
                continue
            if any(p.get("id") == new_piece.get("id") for p in piece_items):
                _upsert(piece_items, new_piece)
                updated += 1
        if updated:
            self._mark_dirty()
            char_name = CHAR_NAMES.get(char_id, f"Character {char_id}")
            self.log_callback(f"[LIVE] Unequipped {updated} pieces from {char_name}")

    @staticmethod
    def _reward_pieces(data: dict) -> list:
        """
        Find fragments paid as a reward. They arrive as a `pieces` dict of `{diff, doc}` pairs, a level down in `item_result` or `return_info`.

        Args:
            data: The server reply.

        Returns:
            The piece documents found. `auto_disassemble_piece` fragments are never included because they do not reach the inventory.
        """
        carriers = [data.get("item_result")]
        nested = data.get("return_info")
        if isinstance(nested, dict):
            carriers.extend(nested.values())
        found = []
        for carrier in carriers:
            rows = carrier.get("pieces") if isinstance(carrier, dict) else None
            found.extend(_docs(rows))
        return found

    def _apply_pieces_create(self, new_pieces):
        """
        Append newly created pieces (forge, fuse, reward) that the inventory does not hold yet.

        Args:
            new_pieces: A list of piece documents.
        """
        if not isinstance(new_pieces, list):
            return
        piece_items = self.inventory_data["piece_items"]
        existing_ids = {p.get("id") for p in piece_items}
        added = []
        for piece in new_pieces:
            if isinstance(piece, dict) and piece.get("id") is not None and piece["id"] not in existing_ids:
                piece_items.append(piece)
                existing_ids.add(piece["id"])
                added.append(piece)
        if not added:
            return
        self._mark_dirty()
        if len(added) == 1:
            self.log_callback(f"[LIVE] Created {self._describe_piece(added[0])}")
        else:
            self.log_callback(f"[LIVE] Created {len(added)} pieces")

    def _apply_totals(self, result: dict):
        """
        Write item and currency totals from a `{items, currency}` envelope. `doc.amount` is the new total, so it is written in and never added.

        Args:
            result: The envelope from `add_result`, `item_result` or `dec_result`.
        """
        held = self.inventory_data.setdefault("items", []) if self.inventory_data is not None else None
        if isinstance(held, list):
            for doc in _docs(result.get("items")):
                if "res_id" in doc:
                    _upsert(held, doc, "res_id")
                    self._mark_dirty()

        held = self.character_data.setdefault("currencies", {}) if self.character_data is not None else None
        if isinstance(held, dict):
            for doc in _docs(result.get("currency")):
                if "res_id" in doc:
                    held[str(doc["res_id"])] = doc
                    self._mark_dirty()

    @staticmethod
    def _entry_identity(entry):
        """Identity of one `characters` entry. Partner cards carry an instance `id` and characters are told apart by `res_id`."""
        if not isinstance(entry, dict):
            return None
        if "id" in entry:
            return ("id", entry["id"])
        return ("res", entry.get("res_id"))

    def _merge_character_data(self, data: dict):
        """
        Fold an incoming `characters` payload into the cached one.

        A payload that covers every cached entry is the full roster and replaces the cache. A narrower one is a delta, so its entries overwrite or
        join the cached ones and everything else (user, currencies) is kept.

        Args:
            data: The server reply holding a `characters` list.
        """
        incoming = data.get("characters") or []
        cached = (self.character_data or {}).get("characters")
        if not isinstance(cached, list) or not cached:
            self.character_data = data
            return
        if {self._entry_identity(e) for e in cached} <= {self._entry_identity(e) for e in incoming}:
            self.character_data = data
            return
        merged = list(cached)
        for entry in incoming:
            _upsert(merged, entry, self._entry_identity)
        self.character_data["characters"] = merged

    def _check_for_relaunch(self, user):
        """
        Start a new snapshot file when the game has been relaunched.

        The marker is `user.last_login_tm`. A reconnect reopens the socket and re-sends `helo` but does not log in again, so it keeps the same value.
        Dropping `saved_path` is the whole rotation. The cached data is kept because the login burst rewrites it.

        Args:
            user: The `user` record from a server reply.
        """
        if not isinstance(user, dict):
            return
        stamp = user.get("last_login_tm")
        if stamp is None or stamp == self.login_stamp:
            return
        was, self.login_stamp = self.login_stamp, stamp
        if was is None or self.saved_path is None:
            return
        self.log_callback("Game relaunched - starting a new snapshot")
        self.saved_path = None

    def _load_rescue(self) -> dict:
        """
        Read the rescue file this capture continues, picking the most recent one on first use.

        Returns:
            The stored document, or an empty one with no records.
        """
        if not self.rescue_path:
            existing = sorted(self.output_dir.glob("rescue_records_*.json"), key=lambda p: p.stat().st_mtime)
            self.rescue_path = existing[-1] if existing else self.output_dir / f"rescue_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        if self.rescue_path.exists():
            try:
                with open(self.rescue_path, encoding="utf-8") as f:
                    doc = json.load(f)
                if isinstance(doc, dict):
                    doc.setdefault("records", [])
                    return doc
            except Exception:
                pass
        return {"records": []}

    def _write_rescue(self, doc: dict, key: str):
        """
        Write the rescue document and tell the UI.

        Args:
            doc: The full document to store.
            key: The reply key the latest change came from.
        """
        doc["capture_time"] = datetime.now().isoformat()
        doc["source_key"] = key
        doc["session_start"] = self.session_start
        with open(self.rescue_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
        self.log_callback(f"[RESCUE] Saved: {len(doc['records'])} rescue records -> {self.rescue_path.name}")
        self.on_saved("rescue")

    def _save_rescue_data(self, key: str, records):
        """Save rescue/gacha records, accumulating across pages and sessions and never dropping old ones."""
        doc = self._load_rescue()
        seen = {_rescue_record_key(r) for r in doc["records"]}
        fetches = doc.setdefault("pool_fetches", {})
        now = int(time.time())
        for record in records if isinstance(records, list) else [records]:
            if not isinstance(record, dict):
                continue
            if record.get("gacha_id"):
                fetches[str(record["gacha_id"])] = now
            key_str = _rescue_record_key(record)
            if key_str not in seen:
                doc["records"].append(record)
                seen.add(key_str)
        self._write_rescue(doc, key)

    def _on_gacha_history(self, data: dict, request: PendingRequest):
        """
        Name the banner of a history page. The records are saved, and the banner marked refreshed, afterwards by the generic rescue handling.

        Args:
            data: The `gacha/history` reply.
            request: The request it answers, whose `id` param is the banner.
        """
        pool = request.params.get("id")
        if not pool:
            return
        pool = str(pool)
        for key in RESCUE_KEYS:
            records = data.get(key)
            if isinstance(records, list):
                for record in records:
                    if isinstance(record, dict) and not record.get("gacha_id"):
                        record["gacha_id"] = pool

    def _on_gacha_list(self, data: dict, request: PendingRequest):
        """
        Keep the server's pity counters, one entry per pity group.

        Args:
            data: The `gacha/get_list` reply.
            request: The request it answers.
        """
        entries = data.get(PITY_KEY)
        if not isinstance(entries, list):
            return
        doc = self._load_rescue()
        pity = doc.setdefault("pity", {})
        for entry in entries:
            if isinstance(entry, dict) and entry.get("res_id"):
                pity[str(entry["res_id"])] = {
                    "pity_ssr_count": entry.get("pity_ssr_count", 0),
                    "pity_sr_count": entry.get("pity_sr_count", 0),
                    "mileage": entry.get("mileage", 0),
                    "updated_at": entry.get("updateAt"),
                }
        self._write_rescue(doc, PITY_KEY)

    def _on_battle_info(self, battle_info: dict):
        """Save enemy stats when a new battle begins."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.battle_path = self.output_dir / f"battle_{ts}.json"
        monster_stat = battle_info.get("monsterStat", {}).get("info", {})
        chars = battle_info.get("chars", [])
        self.battle_data = {
            "capture_time": datetime.now().isoformat(),
            "enemy_def": monster_stat.get("S_DEF", 0),
            "enemy_atk": monster_stat.get("S_ATK", 0),
            "enemy_dmg_decrease": monster_stat.get("S_DMG_DECREASE_RATE", 0.0),
            "battle_result": None,
            "mvp_res_id": None,
            "char_dpt": {},
            "player_chars": [
                {
                    "res_id": c.get("res_id"),
                    "atk": c.get("status", {}).get("info", {}).get("S_ATK", 0),
                    "def": c.get("status", {}).get("info", {}).get("S_DEF", 0),
                    "cri": c.get("status", {}).get("info", {}).get("S_CRI", 0),
                    "cri_dmg": c.get("status", {}).get("info", {}).get("S_CRI_DMG_RATE", 0),
                }
                for c in chars
            ],
        }
        self._write_battle_file()
        self.log_callback(
            f"[BATTLE] Started: enemy DEF={self.battle_data['enemy_def']} ATK={self.battle_data['enemy_atk']}"
        )

    def _on_return_info(self, return_info: dict):
        """Update battle result on battle end."""
        if not self.battle_data:
            return
        result = return_info.get("result", "")
        mvp = str(return_info.get("mvp") or "")
        self.battle_data["battle_result"] = result
        self.battle_data["mvp_res_id"] = mvp
        self._write_battle_file()
        self.log_callback(f"[BATTLE] Result: {result}, MVP res_id={mvp}")

    def _on_snapshot(self, snapshot: dict):
        """Update per-character DPT from snapshot if non-zero data is available."""
        if not self.battle_data:
            return
        dpt = snapshot.get("cache", {}).get("battle_wt", {}).get("dpt", {})
        char_stats = dpt.get("char_stats", {})
        if not char_stats:
            return
        if any(v.get("damage", 0) > 0 for v in char_stats.values() if isinstance(v, dict)):
            self.battle_data["char_dpt"] = {
                str(k): int(v.get("damage", 0))
                for k, v in char_stats.items()
                if isinstance(v, dict)
            }
            self._write_battle_file()

    def _write_battle_file(self):
        """Write current battle data to timestamped file and battle_latest.json."""
        if not self.battle_path or not self.battle_data:
            return
        try:
            with open(self.battle_path, "w", encoding="utf-8") as f:
                json.dump(self.battle_data, f, indent=2)
            latest_path = self.output_dir / "battle_latest.json"
            with open(latest_path, "w", encoding="utf-8") as f:
                json.dump(self.battle_data, f, indent=2)
            self.on_saved("battle")
        except Exception as e:
            self.log_callback(f"[BATTLE] Write error: {e}")

    def done(self):
        """Cleanup on shutdown."""
        if self.debug_file:
            self.debug_file.close()
            self.debug_file = None
