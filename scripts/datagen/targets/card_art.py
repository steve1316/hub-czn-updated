"""
Per-character art: deck builder card images, simulator card icons, and the Android full illustration.

Images are only ever added, never re-encoded, so a run over unchanged data touches no binary files. `--refresh-art`
re-encodes them. The deck builder's image map is rebuilt from the files that exist plus the ones being added.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.datagen import roster
from scripts.datagen.art import wanted, webp
from scripts.datagen.naming import slug
from scripts.datagen.overrides import Issue
from scripts.datagen.runner import REPO_ROOT, Context, TargetResult

NAME = "card_art"
OFFLINE = True

COMBATANT_TABLE = "char_base@char_combatant.json"

DECK_BUILDER_DIR = Path("src/pages/deck-builder/data")
COMBATANTS_DIR = DECK_BUILDER_DIR / "combatants"
IMAGE_MAP_PATH = DECK_BUILDER_DIR / "deck-builder-card-images.ts"
ICONS_DIR = Path("api/assets/cards")
ANDROID_COLLAPSE_DIR = Path("android-app/app/src/main/assets/collapse")

# The simulator's card icons are thumbnails of the full illustration.
ICON_SIZE = (120, 180)
ICON_QUALITY = 85
DECK_BUILDER_QUALITY = 90

# The deck builder shows a combatant's starting cards, epiphany cards and ego skill. Variants reuse their base card's art.
_CARD_COLUMNS = [f"start_{n}_link_card_id" for n in range(1, 5)] + [f"spark_card_{n}_link_card_id" for n in range(1, 5)]
_CARD_COLUMNS.append("collapse_skill_link_card_id")

# Cards a combatant creates (Sword Tassel), transforms into (Shard:Light) or gets on collapse (Daze, `_col`, which no row links to) are
# shown by the Guides. Epiphany variants (`_rsp`) are not.
_EXTRA_CARD = re.compile(r"^c_(\d+)_(?:col|cre\d+|[a-z]+\d+_mut\d+)$")

_CARD_FILE = re.compile(r"^(c_(\d+)_\w+)\.webp$")


def build(ctx: Context) -> TargetResult:
    """
    Generate missing art for every shipped combatant, and the deck builder's image map.

    Args:
        ctx: The run context.

    Returns:
        The image map as a normal file, the images as files created only when missing, and a summary.
    """
    combatants = ctx.client.by_id(COMBATANT_TABLE)
    folders = _existing_folders()
    new_files: dict[Path, bytes] = {}
    issues: list[Issue] = []
    for res_id, character in roster.by_name():
        row = combatants.get(str(res_id), {})
        folder = folders.get(res_id) or slug(character["name"])
        for card_id in [row.get(column) for column in _CARD_COLUMNS] + extra_cards(ctx, res_id):
            card = ctx.client.cards.get(card_id or "")
            source = ctx.client.illustration(card) if card else None
            if source is None:
                continue
            deck_path = COMBATANTS_DIR / folder / f"{card_id}.webp"
            if wanted(ctx, deck_path):
                new_files[deck_path] = webp(source, quality=DECK_BUILDER_QUALITY)
            icon_path = ICONS_DIR / f"{source.stem}.webp"
            if wanted(ctx, icon_path):
                new_files[icon_path] = webp(source, quality=ICON_QUALITY, size=ICON_SIZE)
        android = _android_collapse(ctx, res_id)
        if android is None:
            issues.append(Issue("warning", f"{NAME}: no full illustration in the client for {character['name']} ({res_id})"))
        else:
            target = ANDROID_COLLAPSE_DIR / android.name
            if wanted(ctx, target) and not _has_android_collapse(res_id):
                new_files[target] = android.read_bytes()

    image_map = _image_map(set(new_files))
    summary = f"{len(roster.combatants())} characters, {len(new_files)} image(s) to add, {len(image_map)} mapped deck builder cards"
    return TargetResult({IMAGE_MAP_PATH: _render_map(image_map)}, summary, issues, new_files=new_files)


def extra_cards(ctx: Context, res_id: int) -> list[str]:
    """
    The combatant's own created, transformed and collapse cards.

    Args:
        ctx: The run context.
        res_id: The combatant.

    Returns:
        Their card ids, sorted.
    """
    return sorted(card_id for card_id in ctx.client.cards if (match := _EXTRA_CARD.match(card_id)) and int(match.group(1)) == res_id)


def _android_collapse(ctx: Context, res_id: int) -> Path | None:
    """
    The illustration the Android Combatants screen shows, which prefers the `_02` render and falls back to `_01`.

    Args:
        ctx: The run context.
        res_id: The combatant.

    Returns:
        The client PNG, copied to Android under the same name, or None when the client has neither render.
    """
    for variant in ("02", "01"):
        source = ctx.client.root / "collapse" / "collapse_illustration" / f"collapse_{res_id}_{variant}.png"
        if source.is_file():
            return source
    return None


def _has_android_collapse(res_id: int) -> bool:
    """Whether Android already has either render, so a character with only `_01` is not given a second one."""
    return any((REPO_ROOT / ANDROID_COLLAPSE_DIR / f"collapse_{res_id}_{variant}.png").exists() for variant in ("01", "02"))


def _existing_folders() -> dict[int, str]:
    """
    Which deck builder folder each combatant's images already live in.

    Returns:
        res_id -> folder name, for every combatant with at least one image.
    """
    folders: dict[int, str] = {}
    root = REPO_ROOT / COMBATANTS_DIR
    for folder in sorted(root.iterdir()) if root.is_dir() else []:
        for image in folder.glob("c_*.webp"):
            match = _CARD_FILE.match(image.name)
            if match:
                folders.setdefault(int(match.group(2)), folder.name)
    return folders


def _image_map(adding: set[Path]) -> dict[str, str]:
    """
    card id -> image path for every combatant card image, existing or about to be added.

    Args:
        adding: Repo-relative paths of images this run adds.

    Returns:
        The map, sorted by card id.
    """
    root = REPO_ROOT / COMBATANTS_DIR
    paths = {path.relative_to(REPO_ROOT) for path in root.glob("*/*.webp")} | {path for path in adding if path.parent.parent == COMBATANTS_DIR}
    entries = {}
    for path in paths:
        match = _CARD_FILE.match(path.name)
        if match:
            entries[match.group(1)] = f"combatants/{path.parent.name}/{path.name}"
    return dict(sorted(entries.items()))


def _render_map(image_map: dict[str, str]) -> bytes:
    """
    The image map module, which the deck builder falls back to when it cannot find an image by file name.

    Args:
        image_map: card id -> image path.

    Returns:
        TypeScript source.
    """
    body = "\n".join(f'  "{card_id}": "{path}",' for card_id, path in image_map.items())
    return f"export const DECK_BUILDER_CARD_IMAGE_BY_ID: Record<string, string> = {{\n{body}\n}}\n".encode("utf-8")
