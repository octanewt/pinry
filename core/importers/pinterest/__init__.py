"""Read boards and pins from Pinterest's "Request your data" export.

Pinterest has changed the export's layout over time, so ``read_export``
looks at what it was given and picks the parser for that layout:

- ``single_page.SinglePageExport``: one HTML page (exports up to 2025).
- ``folder.FolderExport``: a folder or .zip of numbered pages (2026).

Both share the record format and value handling in ``common``. Only the
Boards and Pins data is read; the rest of the account data in the export
(email, login history, messages and so on) is ignored.
"""
from core.importers.pinterest.common import (
    ExportBoard, ExportFormatError, ExportPin, description, image_urls,
    import_items,
)
from core.importers.pinterest.folder import FolderExport
from core.importers.pinterest.single_page import SinglePageExport
from core.importers.pinterest.sources import open_source

PARSERS = (FolderExport, SinglePageExport)

__all__ = [
    "ExportBoard", "ExportFormatError", "ExportPin", "FolderExport",
    "PARSERS", "SinglePageExport", "description", "detect", "image_urls",
    "import_items", "read_export",
]


def detect(source):
    """The parser class for ``source``'s layout."""
    for parser in PARSERS:
        if parser.sniff(source):
            return parser
    raise ExportFormatError(
        "Not a Pinterest data export this command understands. Give it "
        "the export's HTML file (older exports) or the export's folder or "
        ".zip (newer exports, with boards and pins folders)."
    )


def read_export(path):
    """Return ``(parser_class, boards, pins)`` for the export at ``path``.

    Raises OSError if it can't be read and ExportFormatError if it isn't
    a Pinterest export in a known layout.
    """
    source = open_source(path)
    try:
        parser = detect(source)
        boards, pins = parser(source).read()
    finally:
        source.close()
    return parser, boards, pins
