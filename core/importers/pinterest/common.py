"""What every layout of Pinterest's "Request your data" export shares.

Pinterest has shipped the export in more than one layout (see
``single_page`` and ``folder``), but the records are the same: each board
and pin is a link followed by ``Key: value`` lines with the same keys in
the same order. Values can contain line breaks, so fields are found in
that order rather than by splitting lines. A layout's parser subclasses
``ExportParser`` and supplies only what differs: how to find the pages,
how an entry starts, how fields are separated and how true and false are
spelled.
"""
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from core.importers.importer import ImportBoard, ImportPin

NO_DATA = ("", "No data", "None")

BOARD_FIELDS = (
    "Created at", "Category", "Description", "Private", "Protected",
    "Collaborators",
)
PIN_FIELDS = (
    "Title", "Details", "Image", "Is Native", "Board Id", "Board Name",
    "Is Video", "Ip Address", "Username", "Alt Text", "Canonical Link",
    "Story Pin Media", "Video", "Created at", "Alive", "Is a repin",
    "Private",
)

_HREF = re.compile(r'<a href="([^"]*)"')
_IMAGE_ID = re.compile(r"[0-9a-f]{32}")
_TAG = re.compile(r"<[^>]+>")


class ExportFormatError(Exception):
    """The file isn't a Pinterest data export this reader understands."""


@dataclass
class ExportBoard:
    name: str
    url: str
    private: bool
    created: datetime = None


@dataclass
class ExportPin:
    id: str
    board_name: str
    image_id: str
    title: str = ""
    details: str = ""
    alt_text: str = ""
    link: str = ""
    private: bool = False
    created: datetime = None


def _spans(pattern, text):
    """Yield each match of ``pattern`` with where the next one starts."""
    heads = list(pattern.finditer(text))
    ends = [head.start() for head in heads[1:]] + [len(text)]
    for head, end in zip(heads, ends[:len(heads)], strict=True):
        yield head, end


def _strip_end(chunk):
    # The last field of an entry runs into the separator before the next.
    return re.sub(r"(<br>\s*)+$", "", chunk.rstrip())


def _link(value):
    """The first http(s) link in a field value, or ""."""
    match = _HREF.search(value)
    if not match:
        return ""
    url = html.unescape(match.group(1)).strip()
    if urlparse(url).scheme.lower() not in ("http", "https"):
        return ""
    return url


class ExportParser(object):
    """Reads boards and pins; subclasses describe one export layout."""

    #: Shown by the command, so it's clear which layout was detected.
    label = ""
    #: How the layout spells true and false.
    true = "True"
    false = "False"
    #: The 2025 layout ends most values with a comma that isn't data.
    trailing_comma = False
    #: Match an entry's link up to the first field's ``Key: ``. Group 1
    #: is the board URL or pin id; boards have the name in group 2.
    board_head = None
    pin_head = None

    def __init__(self, source):
        self.source = source

    @classmethod
    def sniff(cls, source):
        """Whether ``source`` (an ``ExportSource``) is in this layout."""
        raise NotImplementedError

    def read(self):
        """Return ``(boards, pins)`` from the source."""
        raise NotImplementedError

    def field_marker(self, name):
        """A regex for the separator before field ``name``'s value."""
        raise NotImplementedError

    # Shared reading.

    def _fields(self, chunk, names):
        """Read ``names`` from ``chunk`` in order; the first has no
        prefix."""
        values = {}
        rest = chunk
        for name, following in zip(names, names[1:] + (None,), strict=True):
            if following is None:
                values[name] = rest
                break
            match = self.field_marker(following).search(rest)
            if match is None:
                raise ExportFormatError("Missing field %r" % following)
            values[name] = rest[:match.start()]
            rest = rest[match.end():]
        return values

    def _entries(self, text, head_pattern):
        for head, end in _spans(head_pattern, text):
            yield head, _strip_end(text[head.end():end])

    def _text(self, value):
        """Turn an HTML field value into plain text, or "" for no data."""
        value = value.strip()
        if self.trailing_comma and value.endswith(","):
            value = value[:-1]
        value = re.sub(r"\s*<br>\s*", "\n", value)
        value = html.unescape(_TAG.sub("", value)).replace("﻿", "")
        value = value.strip()
        return "" if value in NO_DATA else value

    def _flag(self, value):
        """True or False, or None when the value isn't either.

        Only the leading word counts: the last field of the last entry
        runs straight into whatever follows it in the page.
        """
        match = re.match(r"\s*(\w+)", value)
        word = match.group(1) if match else None
        if word == self.true:
            return True
        if word == self.false:
            return False
        return None

    def _private(self, value):
        # Anything that isn't clearly public is treated as private, so a
        # misread flag can't publish something that was private on
        # Pinterest.
        return self._flag(value) is not False

    def _date(self, value):
        value = self._text(value)
        try:
            parsed = datetime.strptime(value, "%Y/%m/%d %H:%M:%S")
        except ValueError:
            return None
        return parsed.replace(tzinfo=timezone.utc)

    def parse_boards(self, text):
        boards = []
        for head, chunk in self._entries(text, self.board_head):
            values = self._fields(chunk, BOARD_FIELDS)
            boards.append(ExportBoard(
                name=self._text(head.group(2)),
                url=html.unescape(head.group(1)),
                # Protected boards are ads-only boards; treat them as
                # private.
                private=self._private(values["Private"])
                or self._flag(values["Protected"]) is True,
                created=self._date(values["Created at"]),
            ))
        return boards

    def parse_pins(self, text):
        pins = []
        for head, chunk in self._entries(text, self.pin_head):
            values = self._fields(chunk, PIN_FIELDS)
            image_id = self._text(values["Image"]).lower()
            pins.append(ExportPin(
                id=head.group(1),
                board_name=self._text(values["Board Name"]),
                image_id=image_id if _IMAGE_ID.fullmatch(image_id) else "",
                title=self._text(values["Title"]),
                details=self._text(values["Details"]),
                alt_text=self._text(values["Alt Text"]),
                link=_link(values["Canonical Link"]),
                private=self._private(values["Private"]),
                created=self._date(values["Created at"]),
            ))
        return pins


def image_urls(image_id):
    """Candidate download URLs for an export image id, best first.

    Pinterest keeps the original under its own extension, which the export
    doesn't record, so try the common ones before the 736px-wide copy,
    which is always a JPEG. Some old pins have lost the original and the
    736px copy but still have smaller ones, so those come last.
    """
    path = "%s/%s/%s/%s" % (
        image_id[0:2], image_id[2:4], image_id[4:6], image_id,
    )
    urls = [
        "https://i.pinimg.com/originals/%s.%s" % (path, ext)
        for ext in ("jpg", "png", "gif", "webp")
    ]
    urls.extend(
        "https://i.pinimg.com/%s/%s.jpg" % (size, path)
        for size in ("736x", "564x", "474x", "236x")
    )
    return urls


def description(pin):
    """The title on the first line, then the details; alt text if neither."""
    parts = [pin.title]
    if pin.details and pin.details != pin.title:
        parts.append(pin.details)
    text = "\n\n".join(part for part in parts if part)
    return text or pin.alt_text


def import_items(boards, pins):
    """Turn parsed export data into importer items.

    Pins without an image id (blank records in the export) are left out.
    """
    return (
        [ImportBoard(name=board.name, private=board.private)
         for board in boards],
        [ImportPin(
            source_id="pinterest:%s" % pin.id,
            board_name=pin.board_name,
            image_urls=image_urls(pin.image_id),
            description=description(pin),
            link=pin.link,
            private=pin.private,
            created=pin.created,
        ) for pin in pins if pin.image_id],
    )
