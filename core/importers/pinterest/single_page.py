"""The 2025 export layout: one HTML page for the whole account.

Each kind of data is an ``<h1>`` section of the page; only Boards and
Pins are read. Fields are ``\\n<br>Key: value`` lines, most values end
with a comma, and flags are ``True`` or ``False``.
"""
import re

from core.importers.pinterest.common import ExportParser, _spans

_SECTION = re.compile(r"<h1[^>]*>([^<]*)</h1>")


def _sections(page):
    """Map each <h1> section title to its HTML."""
    sections = {}
    for head, end in _spans(_SECTION, page):
        sections.setdefault(head.group(1).strip(), page[head.end():end])
    return sections


class SinglePageExport(ExportParser):
    label = "single HTML page (2025 layout)"
    true = "True"
    false = "False"
    trailing_comma = True
    board_head = re.compile(
        r'<a href="(https://www\.pinterest\.com/[^"/]+/[^"/]+/)">([^<]*)</a>'
        r'\n<br>Created at: '
    )
    pin_head = re.compile(
        r'<a href="https://www\.pinterest\.com/pin/(\d+)/">'
        r'https://www\.pinterest\.com/pin/\1/</a>\n<br>Title: '
    )

    @classmethod
    def sniff(cls, source):
        if source.page is None:
            return False
        sections = _sections(source.page)
        return "Boards" in sections and "Pins" in sections

    def field_marker(self, name):
        return re.compile(re.escape("\n<br>%s: " % name))

    def read(self):
        sections = _sections(self.source.page)
        return (
            self.parse_boards(sections["Boards"]),
            self.parse_pins(sections["Pins"]),
        )
