"""
Installing character art from an arbitrary local image.

This is the fallback used when the unpacked client is not available, so the image handed in can be
any shape. These check it ends up the exact shape the app expects.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

pytest.importorskip("PIL", reason="Pillow is needed to process images")

import install_portrait  # noqa: E402
from PIL import Image  # noqa: E402


@pytest.fixture
def assets(tmp_path, monkeypatch):
    """Point the installer at a temp asset tree so tests never touch the real one."""
    monkeypatch.setattr(install_portrait, "ASSET_ROOT", tmp_path)
    monkeypatch.setattr(install_portrait, "REPO_ROOT", tmp_path)
    return tmp_path


def _image(tmp_path, size, name="src.png"):
    path = tmp_path / name
    Image.new("RGB", size, (10, 120, 200)).save(path)
    return path


@pytest.mark.parametrize("source_size", [(400, 220), (64, 64), (1000, 1000), (120, 900)])
def test_face_always_ends_up_the_right_size(assets, tmp_path, source_size):
    out = install_portrait.install(30113, _image(tmp_path, source_size), install_portrait.FACE, force=False)
    with Image.open(out) as im:
        assert im.size == (72, 72)
        assert im.mode == "RGBA"


def test_skill_icon_is_not_square(assets, tmp_path):
    out = install_portrait.install(30113, _image(tmp_path, (500, 500)), install_portrait.TP_SKILL, force=False)
    with Image.open(out) as im:
        assert im.size == (108, 76)


def test_filename_matches_what_the_app_asks_for(assets, tmp_path):
    out = install_portrait.install(30115, _image(tmp_path, (200, 200)), install_portrait.FACE, force=False)
    assert out.name == "bookmark_face_character_map_30115.png"
    assert out.parent.name == "faces"


def test_existing_art_is_not_clobbered(assets, tmp_path):
    src = _image(tmp_path, (200, 200))
    install_portrait.install(30113, src, install_portrait.FACE, force=False)
    with pytest.raises(FileExistsError):
        install_portrait.install(30113, src, install_portrait.FACE, force=False)


def test_force_replaces_it(assets, tmp_path):
    src = _image(tmp_path, (200, 200))
    install_portrait.install(30113, src, install_portrait.FACE, force=False)
    install_portrait.install(30113, src, install_portrait.FACE, force=True)


def test_a_missing_source_is_reported_clearly(assets, tmp_path):
    with pytest.raises(FileNotFoundError):
        install_portrait.install(30113, tmp_path / "nope.png", install_portrait.FACE, force=False)


def test_wide_images_are_cropped_not_squashed(assets, tmp_path):
    # A face built by squashing a wide image looks obviously wrong beside the real assets, so the
    # centre is cropped to a square first.
    path = tmp_path / "halves.png"
    im = Image.new("RGB", (200, 100), (255, 0, 0))
    for x in range(100, 200):
        for y in range(100):
            im.putpixel((x, y), (0, 0, 255))
    im.save(path)

    out = install_portrait.install(30113, path, install_portrait.FACE, force=False)
    with Image.open(out) as result:
        # A centre crop of a 200x100 image keeps x in [50, 150), so the halves stay evenly split.
        left = result.getpixel((10, 36))[:3]
        right = result.getpixel((61, 36))[:3]
        assert left[0] > left[2], "left side should still be red"
        assert right[2] > right[0], "right side should still be blue"
