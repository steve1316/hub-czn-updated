# Adding a Memory Fragment set

Set definitions live in `api/game_data/sets.py::SETS`, and they are typed by hand. The game's own
data is the authoritative source, unpacked the same way as for
[adding a character](adding-a-character.md). Community set lists have been wrong before, and the
table went seven months out of date once because nothing was checking it.

## What you need from the client

Beyond the folders listed in the character guide, sets read three shards and two art folders:

| Path | Holds |
|---|---|
| `db/piece_set_option@piece_set_option.json` | The set table, with its `set2` / `set4` / `set6` tiers |
| `db/item_piece@item_piece.json` | Joins a 7-digit piece res_id to a set option id |
| `text/en/text.json` | Display names and bonus descriptions |
| `img/icon_piece_set_NNN.png` | The small set icon |
| `piece/item_piece_set_NNN_<slot>.png` | The per-slot fragment art, slots 1 to 6 |

## Running the extractor

```
python scripts/extract_sets.py C:\path\to\output
```

It prints one paste-ready line per set. Everything mechanical is resolved for you - id, name, piece
count, icon, and the stat bonuses the optimizer can score. Conditional bonuses come out as the
client's full English description, which is usually longer than the one-line summary the table keeps,
so those lines are marked `# TODO: review`. Shorten them to match the surrounding entries before
pasting.

The extractor only emits sets that `item_piece` actually links to. The client table also holds
faction sets, per-combatant sets, and sets with no pieces in the game yet, and none of those are
fragments a player can own. Set 21 is the current example: it is fully defined but unobtainable, so
it is listed in `UNRELEASED_SETS` in `tests/api/test_set_data.py`.

## How the set id is derived

A piece res_id is seven digits: `11`, then the slot, then the rarity, then a three-digit set id. So
`1154028` is slot 5, rarity 4, set 28. `MemoryFragment.from_json` decodes captures this way, which is
why a set missing from the table shows up as `Unknown(28)`.

## Adding the data

1. Paste the new lines into `SETS`, keeping the column alignment.
2. Run `python scripts/export_sets_json.py` to regenerate the Android asset. Never hand-edit
   `android-app/app/src/main/assets/sets.json` - a test compares it against the table.
3. Copy the art:
   - `img/icon_piece_set_NNN.png` to `api/assets/pieces/`
   - `piece/item_piece_set_NNN_<1..6>.png` to both `api/assets/game/pieces/` and
     `android-app/app/src/main/assets/pieces/`

## The tier model

The client gives a set up to three tiers. The table keeps the highest one as `pieces`, and a
lower stat tier becomes `two_piece`, which the optimizer applies at two pieces. Most sets define one
tier only. **Do not invent a `two_piece` bonus** - `Line of Justice` carried one for months that the
game does not grant, which inflated every build holding two of its pieces.

Six-piece tiers exist in the client but no obtainable set uses one, so the table does not model them.

## Checking your work

```
set CZN_CLIENT_DB=C:\path\to\output
python -m pytest tests/api/test_set_data.py -v
```

With the client present this compares every entry's name, piece count and bonus against the game.
Without it, those checks skip and the rest still run, including a scan of your latest capture for set
ids the table cannot name.
