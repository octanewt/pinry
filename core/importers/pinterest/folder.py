"""The 2026 export layout: a folder (or .zip) with a page per kind of data.

Boards are in ``boards/0001.html`` and pins in ``pins/0001.html``,
``pins/0002.html`` and so on, 4,000 to a page (``pins/your_pins.html``
only links the pages). The HTML is indented: each field is on its own
line, ``Key: value <br>``, and flags are ``Yes`` or ``No``.
"""
import re

from core.importers.pinterest.common import ExportParser


class FolderExport(ExportParser):
    label = "folder of pages (2026 layout)"
    true = "Yes"
    false = "No"
    board_head = re.compile(
        r'<a href="(https://www\.pinterest\.com/[^"/]+/[^"/]+/)">'
        r'\s*([^<]*?)\s*</a>\s*<br>\s*Created at: '
    )
    pin_head = re.compile(
        r'<a href="https://www\.pinterest\.com/pin/(\d+)/">'
        r'\s*https://www\.pinterest\.com/pin/\1/\s*</a>\s*<br>\s*Title: '
    )

    @classmethod
    def sniff(cls, source):
        return source.has_category("boards") and source.has_category("pins")

    def field_marker(self, name):
        # "<br>" ends the previous value's line; the key starts the next.
        # A key with an empty value can have no space after the colon.
        return re.compile(
            r"\s*<br>[ \t]*\n[ \t]*%s:[ \t]?" % re.escape(name)
        )

    def read(self):
        boards = []
        for page in self.source.category_pages("boards"):
            boards.extend(self.parse_boards(page))
        pins = []
        for page in self.source.category_pages("pins"):
            pins.extend(self.parse_pins(page))
        return boards, pins
