"""
Where the extracted game client DB lives.

It is not shipped with the app - it comes from unpacking the game's own data files, so most machines
do not have it. The optimizer's precise damage classifier, the effect indexes and the character
extraction scripts all read it, and each falls back quietly when it is absent.

Set CZN_CLIENT_DB to the extracted output folder, the one containing `db/` and `text/`.
"""

import os
from pathlib import Path

ENV_VAR = "CZN_CLIENT_DB"

# The original author's path. Kept last so their machine keeps working with no configuration, but it
# means every other machine silently got an empty index before this was configurable.
_LEGACY_OUTPUT = Path(r"C:\Users\soste\Downloads\output")


def client_output_dir() -> Path:
    """
    Root of the extracted client data, holding `db/` and `text/`.

    Returns:
        The path from CZN_CLIENT_DB, else a `client_db` folder beside the repo, else the legacy one.
        The path is not guaranteed to exist - callers check.
    """
    env = os.environ.get(ENV_VAR, "").strip()
    if env:
        return Path(env)
    repo_local = Path(__file__).resolve().parent.parent / "client_db"
    if repo_local.exists():
        return repo_local
    return _LEGACY_OUTPUT


def client_db_dir() -> Path:
    """
    The `db/` folder holding the shard JSONs.

    Returns:
        `<client_output_dir()>/db`. Not guaranteed to exist.
    """
    return client_output_dir() / "db"


def have_client_db() -> bool:
    """
    Whether the client DB is actually present.

    Returns:
        True if the `db/` folder exists, so callers can skip or fall back instead of failing.
    """
    return client_db_dir().is_dir()


def client_text_file() -> Path:
    """
    The English text catalogue, which holds display names.

    Returns:
        `<client_output_dir()>/text/en/text.json`. Not guaranteed to exist.
    """
    return client_output_dir() / "text" / "en" / "text.json"


def have_client_text() -> bool:
    """
    Whether the text catalogue is present.

    Separate from `have_client_db` because an export can stop early and leave the shard JSONs
    without it. Anything that resolves names needs this as well.

    Returns:
        True if the catalogue exists.
    """
    return client_text_file().is_file()
