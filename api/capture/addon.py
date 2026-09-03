"""
mitmproxy Addon for intercepting CZN game WebSocket traffic.
Extracts Memory Fragment inventory and character data from game API responses.
"""

import json
import gzip
import zlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from game_data import CHARACTERS, SETS
from game_data.constants import EQUIPMENT_SLOTS

from .constants import SERVERS

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


def _rescue_record_key(record: dict) -> str:
    """Stable dedup key using only semantic fields, tolerating extra fields and type differences."""
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

            if not isinstance(data, dict):
                return

            # Debug: log every decoded message before filtering, tagged with direction
            if self.debug_file:
                entry = {
                    "ts": datetime.now().isoformat(),
                    "dir": direction,
                    "keys": list(data.keys()),
                    "size": len(content),
                    "data": data
                }
                self._write_debug(entry)

            # From here on, only process server-side responses (inventory,
            # battle, rescue pipelines). Client requests have a different
            # schema and would misfire downstream code.
            if msg.from_client:
                return

            if data.get("res") != "ok":
                return

            # Live monitoring: apply piece deltas
            if "piece" in data and self.inventory_data and "piece_items" in self.inventory_data:
                self._apply_piece_delta(data)

            # Check for 'info' structure (new API format)
            if "info" in data:
                info = data.get("info", {})

                # Check for item data in new format
                if isinstance(info, dict) and "item" in info:
                    item_info = info.get("item", {})

                    # Check for piece (Memory Fragment) data
                    if "piece" in item_info:
                        piece_info = item_info.get("piece", {})
                        # Store this as inventory data (new format)
                        if not self.inventory_data:
                            self.inventory_data = {}
                        self.inventory_data["info_item_piece"] = piece_info
                        self._save_data()

                # Check for character data in new format
                if isinstance(info, dict) and "character" in info:
                    char_info = info.get("character", {})
                    if not self.character_data:
                        self.character_data = {}
                    self.character_data["info_character"] = char_info
                    self._save_data()

            # Capture inventory data (Memory Fragments)
            if "piece_items" in data:
                self.inventory_data = data
                self._save_data()

            # Capture character data
            has_characters = "characters" in data and isinstance(data.get("characters"), list)
            has_user = "user" in data

            if has_characters or has_user:
                self.character_data = data
                self._save_data()

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

        except Exception as e:
            self.log_callback(f"Error: {e}")

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
        new_id = new_piece["id"]
        equipped_piece = data.get("equippedPiece")

        # Find old piece for comparison
        old_piece = None
        for i, p in enumerate(piece_items):
            if p["id"] == new_id:
                old_piece = p
                piece_items[i] = new_piece
                break
        else:
            piece_items.append(new_piece)

        # Apply equippedPiece (displaced piece in swap)
        if equipped_piece:
            eq_id = equipped_piece["id"]
            for i, p in enumerate(piece_items):
                if p["id"] == eq_id:
                    piece_items[i] = equipped_piece
                    break
            else:
                piece_items.append(equipped_piece)

        self._save_data()

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

    def _save_rescue_data(self, key: str, records):
        """Save rescue/gacha records, accumulating across pages and sessions."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not self.rescue_path:
            # Continue from the most recent existing file instead of starting fresh
            existing = sorted(self.output_dir.glob("rescue_records_*.json"),
                              key=lambda p: p.stat().st_mtime)
            self.rescue_path = existing[-1] if existing else self.output_dir / f"rescue_records_{ts}.json"

        existing = []
        if self.rescue_path.exists():
            try:
                with open(self.rescue_path) as f:
                    existing_data = json.load(f)
                    existing = existing_data.get("records", [])
            except Exception:
                pass

        existing_strs = {_rescue_record_key(r) for r in existing}
        new_records = list(existing)
        for record in (records if isinstance(records, list) else [records]):
            key_str = _rescue_record_key(record)
            if key_str not in existing_strs:
                new_records.append(record)
                existing_strs.add(key_str)

        save_data = {
            "capture_time": datetime.now().isoformat(),
            "source_key": key,
            "records": new_records,
        }

        with open(self.rescue_path, "w") as f:
            json.dump(save_data, f, indent=2)

        self.log_callback(
            f"[RESCUE] Saved: {len(new_records)} rescue records -> {self.rescue_path.name}"
        )
        self.on_saved("rescue")

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
