"""
Copying character art out of the unpacked client.

The client root can come from an argument or from `CZN_CLIENT_DB`, and an export that stopped early
leaves a complete `db/` with no `face/`. These check both cases are handled rather than silently
copying nothing.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import extract_portraits  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A client root holding one character's face, with the repo assets pointed at a temp tree."""
    face = tmp_path / "client" / "face" / "character"
    face.mkdir(parents=True)
    (face / "bookmark_face_character_map_30115.png").write_bytes(b"png")
    monkeypatch.setattr(extract_portraits, "DST_BASE", tmp_path / "assets")
    return tmp_path / "client"


def test_the_client_root_can_be_given_as_the_first_argument(tmp_path):
    output_dir, res_ids = extract_portraits.parse_args([str(tmp_path), "30115", "30116"])
    assert output_dir == tmp_path
    assert res_ids == [30115, 30116]


def test_the_client_root_falls_back_to_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("CZN_CLIENT_DB", str(tmp_path))
    output_dir, res_ids = extract_portraits.parse_args(["30115"])
    assert output_dir == tmp_path
    assert res_ids == [30115]


def test_res_ids_are_required():
    with pytest.raises(ValueError):
        extract_portraits.parse_args([])


def test_a_present_face_is_copied_under_its_expected_name(client, tmp_path):
    copied, missing = extract_portraits.copy_for(30115, client)

    assert copied == 1
    assert (tmp_path / "assets" / "faces" / "bookmark_face_character_map_30115.png").is_file()
    # tp_skill sorts late, so an interrupted export has the face but not the icon.
    assert missing == ["tp_skill/battle_icon_tp_skill_30115.png"]


def test_a_character_absent_from_the_client_reports_every_required_file(client):
    copied, missing = extract_portraits.copy_for(99999, client)

    assert copied == 0
    assert len(missing) == 2
