"""
Generators for the game data the app ships, built from the extracted game client instead of by hand.

Run `python -m scripts.datagen --help` for usage. Each module under `targets/` owns one output file or a small group of
them, and `runner.py` decides which to write. See docs/superpowers/specs/2026-10-01-automate-hand-written-data-design.md.
"""

from api.frozen_path import add_vribbels_to_path

# Some game_data modules import their siblings bare (`from game_data.constants import ...`), so api/ must be importable.
add_vribbels_to_path()
