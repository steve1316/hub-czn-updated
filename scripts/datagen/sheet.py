"""
Read the community Google Sheet the Guides page is imported from.

The sheet is public, so its HTML view needs no login. Each tab's HTML is one table whose cells hold text and images in
the positions a reader sees, which is what the guide importer works from. Every download is cached on disk so a re-run
does not hit the network again.
"""

from __future__ import annotations

import hashlib
import html
import re
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

SHEET_ID = "1-KkQUFrjD_2Un3zMDmypCwZFVF5VmowswqYdLt9MOw8"
HTMLVIEW_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/htmlview"
TAB_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/htmlview/sheet?headers=true&gid={{gid}}"
EDIT_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid={{gid}}#gid={{gid}}"

_TAB_ENTRY = re.compile(r'items\.push\(\{name: "((?:[^"\\]|\\.)*)",[^}]*?gid: "(\d+)"')
_TIMEOUT_SECONDS = 60


@dataclass
class Cell:
    """One cell of a sheet tab."""

    # 0-based row index, matching the sheet's row number minus one.
    row: int
    # 0-based column index, where column A is 0.
    col: int
    # The cell's text, with line breaks kept as "\n". Empty when it holds only images.
    text: str = ""
    # URLs of the images placed in the cell.
    images: list[str] = field(default_factory=list)

    @property
    def ref(self) -> str:
        """The cell's address as the sheet shows it, such as "B12"."""
        return f"{column_letters(self.col)}{self.row + 1}"


class Fetcher:
    """Downloads sheet pages and images, caching each one on disk by URL."""

    def __init__(self, cache_dir: Path):
        """
        Args:
            cache_dir: Where downloads are kept between runs.
        """
        self.cache_dir = cache_dir

    def bytes(self, url: str) -> bytes:
        """
        One download, from the cache when it has been fetched before.

        Args:
            url: The address.

        Returns:
            The response body.
        """
        path = self.cache_dir / hashlib.sha1(url.encode("utf-8")).hexdigest()
        if not path.is_file():
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(url, headers={"User-Agent": "hub-czn datagen"})
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                path.write_bytes(response.read())
        return path.read_bytes()

    def text(self, url: str) -> str:
        """
        One page as text.

        Args:
            url: The address.

        Returns:
            The decoded page.
        """
        return self.bytes(url).decode("utf-8")


def column_letters(col: int) -> str:
    """
    A 0-based column index as sheet letters.

    Args:
        col: The index, where 0 is column A.

    Returns:
        Letters such as "A", "Z" or "AA".
    """
    letters = ""
    col += 1
    while col:
        col, remainder = divmod(col - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def tabs(page: str) -> list[tuple[str, str]]:
    """
    The tabs listed by the sheet's HTML view.

    Args:
        page: The `/htmlview` page.

    Returns:
        (tab name, gid) pairs in sheet order.
    """
    return [(html.unescape(name.replace("\\/", "/")), gid) for name, gid in _TAB_ENTRY.findall(page)]


def parse_grid(page: str) -> dict[tuple[int, int], Cell]:
    """
    The cells of one tab's HTML view.

    Args:
        page: The `/htmlview/sheet` page for the tab.

    Returns:
        (row, col) -> cell, for every cell holding text or an image. A merged cell is listed once, at its top-left.
    """
    parser = _GridParser()
    parser.feed(page)
    return {key: cell for key, cell in parser.cells.items() if cell.text.strip() or cell.images}


class _GridParser(HTMLParser):
    """Walks the sheet's table, tracking columns across row and column spans."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells: dict[tuple[int, int], Cell] = {}
        self._row = -1
        self._col = 0
        self._occupied: set[tuple[int, int]] = set()
        self._cell: Cell | None = None
        self._in_table = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "tbody":
            self._in_table = True
        elif not self._in_table:
            return
        elif tag == "tr":
            self._row += 1
            self._col = 0
        elif tag == "td":
            while (self._row, self._col) in self._occupied:
                self._col += 1
            rows, cols = int(attributes.get("rowspan", 1)), int(attributes.get("colspan", 1))
            for r in range(self._row, self._row + rows):
                for c in range(self._col, self._col + cols):
                    self._occupied.add((r, c))
            # The first column of each row is the row-number header, so data columns start at A = 0 after it.
            self._cell = Cell(self._row, self._col - 1)
            self._col += cols
        elif tag == "th" and self._row >= 0:
            # Row headers take up the first column of the grid.
            self._occupied.add((self._row, self._col))
            self._col += 1
        elif tag == "br" and self._cell is not None:
            self._cell.text += "\n"
        elif tag == "img" and self._cell is not None and attributes.get("src"):
            self._cell.images.append(attributes["src"])

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None:
            self._cell.text = self._cell.text.strip()
            self.cells[(self._cell.row, self._cell.col)] = self._cell
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.text += data
