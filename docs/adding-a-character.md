# Adding a new character

The game's own data lives in `bin/appdata/cznlive/data.pack`. It can be unpacked with
[Chaos-Zero-Nightmare-ASSet-Ripper](https://github.com/akioukun/Chaos-Zero-Nightmare-ASSet-Ripper),
and that is the authoritative source for everything below - res_ids, growth curves, and the art.
Use it if you can. Sourcing a character by hand is the fallback, and it has been wrong before.

## Unpacking the client

Point **Open Pack** at `bin/appdata/cznlive/data.pack`, then **Scan Tree**. The tree lists one
folder per asset category, and Ctrl+Right Click multi-selects, so you can pick a few and export only
those.

**Do not export the whole tree.** That is over 5 GB and slow enough that it is easy to interrupt.
Only six folders are ever read:

| Folder | Feeds | Size |
|---|---|---|
| `card_illustration/` | Deck builder card art, only for `extract_card_art.py` | ~400 MB |
| `collapse/collapse_illustration/` | Full-art character illustrations, optional | ~80 MB |
| `db/` | Every character, scaling, potential and monster value | ~180 MB |
| `face/character/` | The 72x72 portraits | tiny |
| `text/en/` | English display names. The equipment pipeline also wants `text/ko/` | tiny |
| `tp_skill/` | The 108x76 battle icons | tiny |

Adding a character needs `db/`, `face/character/`, `text/en/` and `tp_skill/`, which come to roughly
200 MB. Everything else in the tree is art and animation nothing here touches - `effect/` alone is
3.1 GB, and `background/`, `card/` and `cutin/` add another 1.7 GB between them.

Point the repo at the result once and every script and test picks it up:

```
set CZN_CLIENT_DB=C:\path\to\output
```

**A full export writes folders in alphabetical order.** Interrupting one leaves a complete `db/` and
no `face/`, `text/` or `tp_skill/`, since those sort late. It looks like it worked until a script
quietly finds nothing. Selecting only the folders above sidesteps that, but check they are there
either way.

## Getting the data

```
python scripts/extract_combatant.py <output_dir> <res_id>
python scripts/extract_partner.py   <output_dir> <res_id>
```

These read the class, attribute, grade, base stats, growth curve and potential nodes straight out of
the client and print an entry ready to paste. `text/en/text.json` supplies the display name, so
without it you get raw ids.

## Finding the res_id

**Take it from the client, never from a guess.** The ids are not ordered by release date. Fei was
added with a provisional `30111` reasoned from her release window - the client says `30048`, so the
guess would never have matched a real capture.

The playable roster is in `db/char_base@char_base.json`. Diff it against what the repo already
knows to see what is new:

```
python -c "
import sys, json; sys.path.insert(0,'api')
from game_data.characters import CHARACTERS
known = {k for k,v in CHARACTERS.items() if v}
rows = json.load(open('<output_dir>/db/char_base@char_base.json', encoding='utf-8'))
print(sorted({int(r['id']) for r in rows} - known))
"
```

A capture works too, and is the only option without the client. It holds every character you own:

```
python -c "
import sys, json, glob; sys.path.insert(0,'api')
from game_data.characters import CHARACTERS
from game_data.partners import PARTNERS
known = {k for k,v in CHARACTERS.items() if v} | {k for k,v in PARTNERS.items() if v}
f = sorted(glob.glob('api/snapshots/memory_fragments_*.json'))[-1]
chars = json.load(open(f, encoding='utf-8'))['characters']['characters']
print(sorted({c['res_id'] for c in chars if c.get('res_id')} - known))
"
```

Partners are linked to their combatant: a partner row carries `partner_id` pointing at the
combatant's `res_id`, and the combatant's `partner_id` matches the partner row's `id`. That is how
Licinia was identified as Arabella's partner. Ids run combatant then partner, so `30115` Arabella is
followed by `30116` Licinia.

## Adding the data

1. `api/data/char_base_l1.json` - the level 1 stats and which scaling groups apply.
2. `api/game_data/characters.py` or `partners.py` - the entry itself. `base_atk` / `base_def` /
   `base_hp` are the **level 60 with full ascension** value, which must equal what the growth curve
   produces.
3. Run the tests. `tests/api/test_character_data.py` applies table-wide rules to every entry, and
   where `CZN_CLIENT_DB` is set it also checks each res_id and growth curve against the client. A
   made-up id fails there.

## Sourcing without the client

Read the numbers **out of the game**. Community sites are useful for class, attribute and skill
text, but their stat numbers have been wrong or ambiguous more than once:

- They quote level 60 stats that already include ascension and potential nodes, while this repo
  stores the plain level 60 value. Arabella's numbers looked wrong until that was understood.
- The friendship health bonus and the `HP%` potential node were both wrong in this repo for a long
  time, and only reading the game caught them.

Two readings settle a character: **level 1** and **level 60**. Together they identify the growth
curve, which cannot be inferred from class - Arabella is a Striker who grows on the Ranger curve.

## Adding the art

Portraits are static PNGs named by res_id, served from `api/assets/game/`:

```
faces/bookmark_face_character_map_{res_id}.png     72x72,  required
tp_skill/battle_icon_tp_skill_{res_id}.png        108x76,  required
collapse/collapse_{res_id}_01.png                          optional
```

See what is missing:

```
python scripts/check_assets.py
```

With the unpacked client, copy the real assets:

```
python scripts/extract_portraits.py 30115 30116
python scripts/copy_portraits.py     # mirror faces into the Android assets
```

Without it, install an image of any size or shape - it is centre-cropped and resized to fit:

```
python scripts/install_portrait.py 30113 ~/Downloads/hilde.png --tp-skill ~/Downloads/hilde_icon.png
```

A missing portrait is not fatal. The Combatants card, the character picker and the Battle page all
fall back to a generic icon, so the character still works, it just looks plain.
