"""Where an export's pages come from: one file, a folder or a .zip.

The 2025 export was a single HTML file. The 2026 export is a folder (or
the .zip Pinterest delivers it in) with a sub-folder per kind of data,
each holding numbered pages: ``boards/0001.html``, ``pins/0001.html``,
``pins/0002.html`` and so on. The .zip is read in place; nothing is
extracted to disk.
"""
import os
import re
import zipfile

from core.importers.pinterest.common import ExportFormatError

# Pinterest's pages are a few MB each; refuse anything absurd rather than
# reading it into memory.
MAX_PAGE_BYTES = 200 * 1024 * 1024

_PAGE = re.compile(r"^(?:(.*)/)?([a-z_]+)/(\d+)\.html$")


def _decode(data, name):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ExportFormatError("Can't read %s: %s" % (name, e)) from e


class ExportSource(object):
    """The pages of one export, whatever it's stored in."""

    #: The whole export when it's a single HTML file, else None.
    page = None

    def category_pages(self, category):
        """The numbered pages of ``category`` (such as "pins"), in order."""
        return []

    def has_category(self, category):
        return False

    def close(self):
        pass


class FileSource(ExportSource):
    def __init__(self, path):
        if os.path.getsize(path) > MAX_PAGE_BYTES:
            raise ExportFormatError("%s is too large to be an export." % path)
        with open(path, "rb") as f:
            self.page = _decode(f.read(), path)


class FolderSource(ExportSource):
    def __init__(self, root):
        self.root = root

    def _names(self, category):
        folder = os.path.join(self.root, category)
        if not os.path.isdir(folder):
            return []
        return sorted(
            name for name in os.listdir(folder)
            if re.fullmatch(r"\d+\.html", name)
        )

    def has_category(self, category):
        return bool(self._names(category))

    def category_pages(self, category):
        pages = []
        for name in self._names(category):
            path = os.path.join(self.root, category, name)
            if os.path.getsize(path) > MAX_PAGE_BYTES:
                raise ExportFormatError("%s is too large." % path)
            with open(path, "rb") as f:
                pages.append(_decode(f.read(), path))
        return pages


class ZipSource(ExportSource):
    def __init__(self, path):
        self.zip = zipfile.ZipFile(path)
        try:
            self._index()
        except BaseException:
            self.zip.close()
            raise

    def _index(self):
        self._pages = {}
        html_files = []
        for info in self.zip.infolist():
            if info.is_dir():
                continue
            if info.filename.lower().endswith(".html"):
                html_files.append(info)
            match = _PAGE.match(info.filename)
            if match:
                prefix, category, _ = match.groups()
                self._pages.setdefault(prefix or "", {}).setdefault(
                    category, []).append(info)
        # The export may sit at the top of the .zip or in one folder in it.
        roots = [
            prefix for prefix, categories in self._pages.items()
            if "boards" in categories and "pins" in categories
        ]
        self._root = self._pages[roots[0]] if len(roots) == 1 else {}
        if not self._root and len(html_files) == 1:
            # An older single-file export, zipped.
            self.page = self._read(html_files[0])

    def _read(self, info):
        if info.file_size > MAX_PAGE_BYTES:
            raise ExportFormatError("%s is too large." % info.filename)
        return _decode(self.zip.read(info), info.filename)

    def has_category(self, category):
        return bool(self._root.get(category))

    def close(self):
        self.zip.close()

    def category_pages(self, category):
        infos = sorted(self._root.get(category, []),
                       key=lambda info: info.filename)
        return [self._read(info) for info in infos]


def _export_root(folder):
    """The export folder that ``folder`` is, or is directly inside."""
    for candidate in (folder, os.path.dirname(folder)):
        if all(os.path.isdir(os.path.join(candidate, category))
               for category in ("boards", "pins")):
            return candidate
    return None


def open_source(path):
    """An ExportSource for ``path``: the export's folder, any file in it,
    its .zip, or a single-file export.

    Raises OSError if the path can't be read and ExportFormatError if it
    isn't anything an export could be.
    """
    path = os.path.abspath(path)
    if os.path.isdir(path):
        root = _export_root(path)
        if root is None:
            raise ExportFormatError(
                "%s has no boards and pins folders; is it a Pinterest "
                "export?" % path
            )
        return FolderSource(root)
    if not os.path.exists(path):
        raise FileNotFoundError("No such file or folder: %s" % path)
    if zipfile.is_zipfile(path):
        try:
            return ZipSource(path)
        except zipfile.BadZipFile as e:
            raise ExportFormatError("Can't read %s: %s" % (path, e)) from e
    root = _export_root(os.path.dirname(path))
    if root is not None:
        # A page of a folder export, such as start_here.html.
        return FolderSource(root)
    return FileSource(path)
