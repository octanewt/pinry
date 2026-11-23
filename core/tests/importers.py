import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from io import StringIO
from unittest import mock

from django.core.management import call_command, CommandError
from django.test import TestCase

from .helpers import TEST_IMAGE_PATH, create_user
from core.fetch import FetchError, http_error
from core.importers.importer import ImportBoard, ImportPin, PinImporter
from core.importers.pinterest import (
    ExportFormatError, FolderExport, SinglePageExport, description, detect,
    image_urls, import_items, read_export,
)
from core.importers.pinterest.sources import ExportSource
from core.models import Board, Image, Pin

IMAGE_A = "73e95b013574a3e13bc175f5d54d5056"
IMAGE_B = "748b1d1b10e22c58d722b821264f496e"


def _board(user, slug, name, private="False", protected="False"):
    return (
        '<a href="https://www.pinterest.com/%s/%s/">%s</a>\n'
        '<br>Created at: 2015/11/21 05:50:14\n'
        '<br>Category: other\n'
        '<br>Description: None\n'
        '<br>Private: %s\n'
        '<br>Protected: %s\n'
        '<br>Collaborators: <a href="https://www.pinterest.com/%s/">%s</a>'
        % (user, slug, name, private, protected, user, user)
    )


def _pin(pin_id, board, image=IMAGE_A, title="No data", details="No data",
         link=None, created="2024/10/13 15:37:47", private="False"):
    link = ('<a href="%s">%s</a>' % (link, link)) if link else "No data"
    return (
        '<a href="https://www.pinterest.com/pin/%s/">'
        'https://www.pinterest.com/pin/%s/</a>\n'
        '<br>Title: %s,\n'
        '<br>Details: %s,\n'
        '<br>Image: %s,\n'
        '<br>Is Native: No data,\n'
        '<br>Board Id: 1,\n'
        '<br>Board Name: %s,\n'
        '<br>Is Video: No data,\n'
        '<br>Ip Address: 192.0.2.1,\n'
        '<br>Username: someone,\n'
        '<br>Alt Text: No data,\n'
        '<br>Canonical Link: %s,\n'
        '<br>Story Pin Media: No data,\n'
        '<br>Video: No data,\n'
        '<br>Created at: %s\n'
        '<br>Alive: True\n'
        '<br>Is a repin: True\n'
        '<br>Private: %s'
        % (pin_id, pin_id, title, details, image, board, link, created,
           private)
    )


BLANK_PIN = (
    '<a href="https://www.pinterest.comNone">https://www.pinterest.comNone'
    '</a>\n<br>Title: No data,\n<br>Image: No data,\n<br>Private: None'
)


def export_page(boards, pins, blank_tail=True):
    """An export page shaped like Pinterest's, with made-up data."""
    pins_html = "<br><br>".join(pins)
    if blank_tail:
        # Pinterest's own export ends the list like this, with no
        # separator after the last real pin.
        pins_html += BLANK_PIN
    return (
        "<html><body>"
        "<h1 id=a>User profile information</h1><h2 id=b>Email</h2>"
        "someone@example.com"
        "<h1 id=c>Boards</h1>%s"
        "<h1 id=d>Pins</h1>%s"
        "<h1 id=e>Notes</h1>\n<br>"
        "</body></html>"
        % ("<br><br>".join(boards), pins_html)
    )


def parse_export(page):
    """Parse a single-page export held in memory."""
    source = ExportSource()
    source.page = page
    return detect(source)(source).read()


SAMPLE = export_page(
    boards=[
        _board("someone", "recipes", "Recipes &amp; Foodstuff"),
        _board("someone", "secret", "Secret Stuff", private="True"),
        _board("other", "ads", "Ads Board", protected="True"),
    ],
    pins=[
        _pin("100", "Recipes &amp; Foodstuff",
             title="Grape Gummies", details="Easy to make &amp; tasty",
             link="https://example.com/gummies?a=1&amp;b=2"),
        _pin("101", "Recipes &amp; Foodstuff", image=IMAGE_B,
             title="Line one\n<br>\n<br>Line two",
             created="2012/02/06 03:11:52"),
        _pin("102", "Collage Item Pins", link="javascript:alert(1)"),
        _pin("103", "Secret Stuff", private="True"),
    ],
)


class PinterestExportParserTests(TestCase):
    def setUp(self):
        self.boards, self.pins = parse_export(SAMPLE)

    def test_should_read_boards_and_privacy(self):
        self.assertEqual(
            [(b.name, b.private) for b in self.boards],
            [("Recipes & Foodstuff", False), ("Secret Stuff", True),
             ("Ads Board", True)],
        )

    def test_should_read_pin_fields(self):
        pin = self.pins[0]
        self.assertEqual(pin.id, "100")
        self.assertEqual(pin.board_name, "Recipes & Foodstuff")
        self.assertEqual(pin.image_id, IMAGE_A)
        self.assertEqual(pin.title, "Grape Gummies")
        self.assertEqual(pin.details, "Easy to make & tasty")
        self.assertEqual(pin.link, "https://example.com/gummies?a=1&b=2")
        self.assertFalse(pin.private)
        self.assertEqual(
            pin.created, datetime(2024, 10, 13, 15, 37, 47, tzinfo=timezone.utc),
        )

    def test_should_keep_line_breaks_in_values(self):
        self.assertEqual(self.pins[1].title, "Line one\n\nLine two")

    def test_should_drop_non_http_links(self):
        self.assertEqual(self.pins[2].link, "")

    def test_should_read_last_pin_privacy_before_blank_record(self):
        self.assertEqual(len(self.pins), 4)
        self.assertTrue(self.pins[3].private)

    def test_unreadable_privacy_should_count_as_private(self):
        _, pins = parse_export(export_page(
            [], [_pin("1", "B", private="Maybe")], blank_tail=False,
        ))
        self.assertTrue(pins[0].private)

    def test_should_reject_other_pages(self):
        with self.assertRaises(ExportFormatError):
            parse_export("<html><h1>Something else</h1></html>")

    def test_image_urls_should_try_originals_then_smaller_copies(self):
        urls = image_urls(IMAGE_A)
        self.assertEqual(
            urls[0], "https://i.pinimg.com/originals/73/e9/5b/%s.jpg" % IMAGE_A,
        )
        self.assertEqual(
            urls[4], "https://i.pinimg.com/736x/73/e9/5b/%s.jpg" % IMAGE_A,
        )
        self.assertEqual(
            urls[-1], "https://i.pinimg.com/236x/73/e9/5b/%s.jpg" % IMAGE_A,
        )

    def test_description_should_put_title_first(self):
        self.assertEqual(
            description(self.pins[0]), "Grape Gummies\n\nEasy to make & tasty",
        )

    def test_description_should_fall_back_to_alt_text(self):
        pin = self.pins[2]
        pin.alt_text = "A photo"
        self.assertEqual(description(pin), "A photo")


# The 2026 layout: a folder of indented pages. Everything here is made up;
# only the shape follows Pinterest's export.

PAGE_TOP = '''
<!DOCTYPE html>
<html lang="eng">
<head>
    <base target="_blank">
    <meta charset="utf-8"/><title>Subject Access Request Data - %s</title>
</head>
<body>
<div id="main-body">
    <div id="contents">
    <h1 id="0abcd">%s</h1>
'''
PAGE_BOTTOM = '''
    </div>
    <div class="pager">
        <a href="./0002.html" class="btn "
           target="_self">
            Next ›
        </a>
    </div>
</div>
</body>
</html>'''


def _board_2026(user, slug, name, private="No", protected="No",
                description=""):
    return '''
        <a href="https://www.pinterest.com/%s/%s/">
            %s
        </a>
        <br>
        Created at: 2015/11/21 05:50:14<br>
        Category: other<br>
        Description: %s<br>
        Private: %s<br>
        Protected: %s<br>
        Collaborators:
<a href="https://www.pinterest.com/friend/">friend</a>        <br>
        <br>''' % (user, slug, name, description, private, protected)


def _pin_2026(pin_id, board, image=IMAGE_A, title="No data",
              details="No data", link=None, created="2024/10/13 15:37:47",
              private="No"):
    link = ('<a href="%s">%s</a>' % (link, link)) if link else "No data"
    return '''
        <a href="https://www.pinterest.com/pin/%s/">https://www.pinterest.com/pin/%s/</a>
        <br>
        Title: %s <br>
        Details: %s <br>
        Image: %s<br>
        Is Native: No <br>
        Board Id: 1 <br>
        Board Name: %s <br>
        Is Video: No <br>
        Ip Address: 192.0.2.1 <br>
        Username: someone <br>
        Alt Text: No data <br>
        Canonical Link: %s
        <br>
        Story Pin Media: No data <br>
        Video: No data <br>
        Created at: %s <br>
        Alive: Yes <br>
        Is a repin: Yes <br>
        Private: %s
        <br>
        <br>''' % (pin_id, pin_id, title, details, image, board, link,
                   created, private)


def folder_pages(boards, pin_pages):
    """Relative path -> HTML of a made-up 2026 export."""
    pages = {
        "start_here.html": PAGE_TOP % ("", "Start here") + PAGE_BOTTOM,
        "boards/0001.html": (
            PAGE_TOP % ("Boards", "Boards") + "".join(boards) + PAGE_BOTTOM
        ),
        "pins/your_pins.html": (
            PAGE_TOP % ("Your Pins", "Your Pins")
            + '<ul><li><a href="0001.html">Pins 0001</a></li></ul>'
            + PAGE_BOTTOM
        ),
        "notes/0001.html": (
            PAGE_TOP % ("Notes", "Notes") + "someone@example.com"
            + PAGE_BOTTOM
        ),
    }
    for number, pins in enumerate(pin_pages, start=1):
        pages["pins/%04d.html" % number] = (
            PAGE_TOP % ("Pins", "Pins") + "".join(pins) + PAGE_BOTTOM
        )
    return pages


FOLDER_SAMPLE = folder_pages(
    boards=[
        _board_2026("someone", "recipes", "Recipes &amp; Foodstuff",
                    description="Things to cook"),
        _board_2026("someone", "secret", "Secret Stuff", private="Yes"),
        _board_2026("other", "ads", "Ads Board", protected="Yes"),
    ],
    pin_pages=[
        [
            _pin_2026("100", "Recipes &amp; Foodstuff",
                      title="Grape Gummies",
                      details="Easy to make &amp; tasty",
                      link="https://example.com/gummies?a=1&amp;b=2"),
            _pin_2026("101", "Recipes &amp; Foodstuff", image=IMAGE_B,
                      title="Line one\nLine two",
                      created="2012/02/06 03:11:52"),
        ],
        [
            _pin_2026("102", "Collage Item Pins",
                      link="javascript:alert(1)"),
            _pin_2026("103", "Secret Stuff", private="Yes"),
        ],
    ],
)


def write_folder(root, pages):
    for name, page in pages.items():
        path = os.path.join(root, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)


def write_zip(path, pages, prefix=""):
    with zipfile.ZipFile(path, "w") as z:
        for name, page in pages.items():
            z.writestr(prefix + name, page)


class TempDirMixin(object):
    def make_dir(self):
        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path)
        return path


class PinterestFolderExportTests(TempDirMixin, TestCase):
    def setUp(self):
        self.root = self.make_dir()
        write_folder(self.root, FOLDER_SAMPLE)

    def _read(self, path=None):
        return read_export(path or self.root)

    def test_should_detect_folder_layout(self):
        parser, _, _ = self._read()
        self.assertIs(parser, FolderExport)

    def test_should_read_boards_and_privacy(self):
        _, boards, _ = self._read()
        self.assertEqual(
            [(b.name, b.private) for b in boards],
            [("Recipes & Foodstuff", False), ("Secret Stuff", True),
             ("Ads Board", True)],
        )
        self.assertEqual(boards[0].url,
                         "https://www.pinterest.com/someone/recipes/")
        self.assertEqual(
            boards[0].created,
            datetime(2015, 11, 21, 5, 50, 14, tzinfo=timezone.utc),
        )

    def test_should_read_pins_from_every_page(self):
        _, _, pins = self._read()
        self.assertEqual([p.id for p in pins], ["100", "101", "102", "103"])

    def test_should_read_pin_fields(self):
        _, _, pins = self._read()
        pin = pins[0]
        self.assertEqual(pin.board_name, "Recipes & Foodstuff")
        self.assertEqual(pin.image_id, IMAGE_A)
        self.assertEqual(pin.title, "Grape Gummies")
        self.assertEqual(pin.details, "Easy to make & tasty")
        self.assertEqual(pin.link, "https://example.com/gummies?a=1&b=2")
        self.assertFalse(pin.private)
        self.assertEqual(
            pin.created, datetime(2024, 10, 13, 15, 37, 47, tzinfo=timezone.utc),
        )

    def test_should_keep_line_breaks_in_values(self):
        _, _, pins = self._read()
        self.assertEqual(pins[1].title, "Line one\nLine two")

    def test_should_drop_non_http_links(self):
        _, _, pins = self._read()
        self.assertEqual(pins[2].link, "")

    def test_last_pin_privacy_should_stop_before_pager(self):
        _, _, pins = self._read()
        self.assertTrue(pins[3].private)

    def test_unreadable_privacy_should_count_as_private(self):
        root = self.make_dir()
        write_folder(root, folder_pages(
            [_board_2026("someone", "b", "B", private="True")],
            [[_pin_2026("1", "B", private="Maybe")]],
        ))
        _, boards, pins = read_export(root)
        self.assertTrue(boards[0].private)
        self.assertTrue(pins[0].private)

    def test_should_accept_any_page_in_the_folder(self):
        for name in ("start_here.html", "pins/0001.html"):
            with self.subTest(name=name):
                parser, _, pins = self._read(
                    os.path.join(self.root, *name.split("/")))
                self.assertIs(parser, FolderExport)
                self.assertEqual(len(pins), 4)

    def test_should_accept_zip(self):
        for prefix in ("", "2026-10-26_pinterest/"):
            with self.subTest(prefix=prefix):
                path = os.path.join(self.make_dir(), "export.zip")
                write_zip(path, FOLDER_SAMPLE, prefix=prefix)
                parser, boards, pins = read_export(path)
                self.assertIs(parser, FolderExport)
                self.assertEqual((len(boards), len(pins)), (3, 4))

    def test_should_accept_zipped_single_page_export(self):
        path = os.path.join(self.make_dir(), "export.zip")
        write_zip(path, {"pinterest.html": SAMPLE})
        parser, _, pins = read_export(path)
        self.assertIs(parser, SinglePageExport)
        self.assertEqual(len(pins), 4)

    def test_should_reject_folder_without_boards_and_pins(self):
        root = self.make_dir()
        write_folder(root, {"notes/0001.html": "<html></html>"})
        with self.assertRaises(ExportFormatError):
            read_export(root)

    def test_should_reject_unrelated_file(self):
        path = os.path.join(self.make_dir(), "page.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write("<html><h1>Something else</h1></html>")
        with self.assertRaises(ExportFormatError):
            read_export(path)


def _image_bytes():
    with open(TEST_IMAGE_PATH, "rb") as f:
        return f.read()


class ImporterTests(TestCase):
    def setUp(self):
        self.user = create_user("importer")
        self.fetched = []
        patcher = mock.patch("core.models.fetch_url", side_effect=self._fetch)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fetch(self, url, referer=None):
        self.fetched.append(url)
        if url.endswith(".png") or url.endswith(".jpg"):
            return _image_bytes()
        raise FetchError("Could not fetch the image.")

    def _run(self, page=SAMPLE, **kwargs):
        kwargs.setdefault("delay", 0)
        boards, pins = import_items(*parse_export(page))
        return PinImporter(self.user, **kwargs).run(boards, pins)

    def test_should_create_boards_with_privacy(self):
        self._run()
        boards = {b.name: b.private for b in Board.objects.all()}
        self.assertEqual(boards, {
            "Recipes & Foodstuff": False,
            "Secret Stuff": True,
            "Ads Board": True,
            # Named by a pin but missing from the board list.
            "Collage Item Pins": True,
        })

    def test_should_create_pins(self):
        report = self._run()
        self.assertEqual(report.pins_imported, 4)
        self.assertEqual((report.pins_public, report.pins_private), (2, 2))
        pin = Pin.objects.get(source_id="pinterest:100")
        self.assertEqual(pin.submitter, self.user)
        self.assertEqual(pin.description, "Grape Gummies\n\nEasy to make & tasty")
        self.assertEqual(pin.referer, "https://example.com/gummies?a=1&b=2")
        self.assertEqual(pin.url, image_urls(IMAGE_A)[0])
        self.assertEqual(
            pin.published,
            datetime(2024, 10, 13, 15, 37, 47, tzinfo=timezone.utc),
        )
        self.assertEqual(
            list(pin.pins.values_list("name", flat=True)),
            ["Recipes & Foodstuff"],
        )
        self.assertFalse(pin.private)
        self.assertTrue(Pin.objects.get(source_id="pinterest:102").private)
        self.assertIsNone(Pin.objects.get(source_id="pinterest:102").referer)

    def test_pin_on_private_board_should_be_private(self):
        page = export_page(
            [_board("someone", "secret", "Secret", private="True")],
            [_pin("1", "Secret", private="False")],
        )
        self._run(page)
        self.assertTrue(Pin.objects.get().private)

    def test_should_create_oldest_pins_first(self):
        self._run()
        ids = list(Pin.objects.order_by("pk").values_list("source_id", flat=True))
        self.assertEqual(ids[0], "pinterest:101")

    def test_should_skip_pins_imported_before(self):
        self._run()
        self.fetched.clear()
        report = self._run()
        self.assertEqual(report.pins_imported, 0)
        self.assertEqual(report.pins_already_imported, 4)
        self.assertEqual(report.boards_existing, 4)
        self.assertEqual(Pin.objects.count(), 4)
        self.assertEqual(self.fetched, [])

    def test_should_download_shared_image_once(self):
        self._run()
        # Pins 100, 102 and 103 share IMAGE_A.
        self.assertEqual(self.fetched.count(image_urls(IMAGE_A)[0]), 1)
        self.assertEqual(Image.objects.count(), 1)

    def test_should_try_next_url_when_download_fails(self):
        page = export_page([], [_pin("1", "B")])
        with mock.patch("core.models.fetch_url") as fetch:
            fetch.side_effect = [FetchError("nope"), _image_bytes()]
            self._run(page)
        pin = Pin.objects.get()
        self.assertEqual(pin.url, image_urls(IMAGE_A)[1])

    def test_should_report_failures_and_retry_them(self):
        page = export_page([], [_pin("1", "B")])
        with mock.patch("core.models.fetch_url",
                        side_effect=FetchError("nope")):
            report = self._run(page)
        self.assertEqual(report.failed, [("pinterest:1", "nope")])
        self.assertFalse(Pin.objects.exists())
        report = self._run(page)
        self.assertEqual(report.pins_imported, 1)

    def test_should_fall_back_to_smaller_copy(self):
        page = export_page([], [_pin("1", "B")])
        missing = http_error(404)
        with mock.patch("core.models.fetch_url") as fetch:
            fetch.side_effect = [missing] * 6 + [_image_bytes()]
            self._run(page)
        pin = Pin.objects.get()
        self.assertEqual(pin.url, image_urls(IMAGE_A)[6])
        self.assertIn("/474x/", pin.url)

    def test_failure_should_say_what_the_server_answered(self):
        page = export_page([], [_pin("1", "B")])
        errors = [http_error(500)] + [
            http_error(404)
        ] * (len(image_urls(IMAGE_A)) - 1)
        with mock.patch("core.models.fetch_url", side_effect=errors):
            report = self._run(page)
        self.assertEqual(report.failed, [(
            "pinterest:1",
            "Could not fetch the image (HTTP 404, 500 from the image server)",
        )])
        self.assertEqual(report.gone, [])

    def test_pin_with_no_image_left_should_be_reported_as_gone(self):
        page = export_page([], [_pin("1", "B")])
        with mock.patch("core.models.fetch_url",
                        side_effect=http_error(404)):
            report = self._run(page)
        self.assertEqual(report.failed, [])
        self.assertEqual([source for source, _ in report.gone],
                         ["pinterest:1"])
        self.assertFalse(Pin.objects.exists())

    def test_403_from_every_url_should_count_as_gone_if_others_download(self):
        # Pinterest's image server answers 403 for files that don't exist.
        page = export_page([], [_pin("1", "B"), _pin("2", "B", image=IMAGE_B)])
        refused = [http_error(403)] * len(image_urls(IMAGE_A))
        with mock.patch("core.models.fetch_url",
                        side_effect=refused + [_image_bytes()]):
            report = self._run(page)
        self.assertEqual(report.failed, [])
        self.assertEqual([source for source, _ in report.gone],
                         ["pinterest:1"])
        self.assertEqual(report.pins_imported, 1)

    def test_403_from_every_url_should_fail_if_nothing_downloads(self):
        # It could mean Pinterest is refusing downloads, so keep retrying.
        page = export_page([], [_pin("1", "B")])
        with mock.patch("core.models.fetch_url",
                        side_effect=http_error(403)):
            report = self._run(page)
        self.assertEqual(report.gone, [])
        self.assertEqual([source for source, _ in report.failed],
                         ["pinterest:1"])

    def test_404_should_count_as_gone_even_if_nothing_downloads(self):
        page = export_page([], [_pin("1", "B")])
        errors = [http_error(403)] * 5 + [http_error(404)] * (
            len(image_urls(IMAGE_A)) - 5)
        with mock.patch("core.models.fetch_url", side_effect=errors):
            report = self._run(page)
        self.assertEqual(report.failed, [])
        self.assertEqual(len(report.gone), 1)

    def test_network_error_should_not_count_as_gone(self):
        page = export_page([], [_pin("1", "B")])
        errors = [http_error(404)] * (len(image_urls(IMAGE_A)) - 1) + [
            FetchError("Could not fetch the image.")]
        with mock.patch("core.models.fetch_url", side_effect=errors):
            report = self._run(page)
        self.assertEqual(report.gone, [])
        self.assertEqual(len(report.failed), 1)

    def test_force_private_should_make_everything_private(self):
        self._run(force_private=True)
        self.assertFalse(Board.objects.filter(private=False).exists())
        self.assertFalse(Pin.objects.filter(private=False).exists())

    def test_should_add_tags(self):
        self._run(tags=["pinterest"])
        pin = Pin.objects.get(source_id="pinterest:100")
        self.assertEqual(list(pin.tags.names()), ["pinterest"])

    def test_should_make_existing_public_board_private(self):
        board = Board.objects.create(submitter=self.user, name="Secret Stuff")
        report = self._run()
        board.refresh_from_db()
        self.assertTrue(board.private)
        self.assertEqual(report.boards_made_private, 1)

    def test_should_not_make_existing_private_board_public(self):
        board = Board.objects.create(
            submitter=self.user, name="Recipes & Foodstuff", private=True,
        )
        self._run()
        board.refresh_from_db()
        self.assertTrue(board.private)
        self.assertTrue(Pin.objects.get(source_id="pinterest:100").private)

    def test_dry_run_should_change_nothing(self):
        report = self._run(dry_run=True)
        self.assertEqual(report.pins_imported, 4)
        self.assertEqual(report.boards_created, 4)
        self.assertFalse(Board.objects.exists())
        self.assertFalse(Pin.objects.exists())
        self.assertEqual(self.fetched, [])

    def test_should_pause_before_downloads(self):
        sleep = mock.Mock()
        page = export_page([], [_pin("1", "B")])
        boards, pins = import_items(*parse_export(page))
        PinImporter(self.user, delay=1.5, sleep=sleep).run(boards, pins)
        sleep.assert_called_with(1.5)

    def test_items_should_skip_pins_without_image(self):
        page = export_page([], [_pin("1", "B", image="No data")])
        _, pins = import_items(*parse_export(page))
        self.assertEqual(pins, [])

    def test_importer_should_accept_plain_items(self):
        boards = [ImportBoard(name="Plain", private=False)]
        pins = [ImportPin(source_id="x:1", board_name="Plain",
                          image_urls=["https://example.com/a.png"])]
        PinImporter(self.user, delay=0).run(boards, pins)
        self.assertEqual(Pin.objects.get().pins.get().name, "Plain")


class ImportPinterestCommandTests(TestCase):
    def setUp(self):
        self.user = create_user("cmd")
        fd, self.path = tempfile.mkstemp(suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(SAMPLE)
        self.addCleanup(os.remove, self.path)

    def _call(self, *args):
        out = StringIO()
        call_command("import_pinterest", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_should_print_counts(self):
        out = self._call(self.path, "--user", self.user.username, "--dry-run")
        self.assertIn("Found 3 boards and 4 pins", out)
        self.assertIn("Boards: 4 would be created", out)
        self.assertIn("4 would be imported (2 public, 2 private)", out)
        self.assertFalse(Pin.objects.exists())

    def test_should_import(self):
        with mock.patch("core.models.fetch_url", return_value=_image_bytes()):
            out = self._call(self.path, "--user", self.user.username,
                             "--delay", "0", "--tag", "pinterest")
        self.assertIn("4 were imported", out)
        self.assertEqual(Pin.objects.filter(tags__name="pinterest").count(), 4)

    def test_should_list_failed_pins_with_links(self):
        with mock.patch("core.models.fetch_url",
                        side_effect=http_error(500)):
            out = self._call(self.path, "--user", self.user.username,
                             "--delay", "0")
        self.assertIn("4 pins failed; run the import again", out)
        self.assertIn(
            "  https://www.pinterest.com/pin/100/: Could not fetch the image "
            "(HTTP 500 from the image server)", out,
        )

    def test_should_list_gone_pins_separately(self):
        with mock.patch("core.models.fetch_url",
                        side_effect=http_error(404)):
            out = self._call(self.path, "--user", self.user.username,
                             "--delay", "0")
        self.assertIn("4 pins have no image left on Pinterest", out)
        self.assertIn("  https://www.pinterest.com/pin/100/\n", out)
        self.assertNotIn("pins failed", out)

    def test_should_reject_unknown_user(self):
        with self.assertRaises(CommandError):
            self._call(self.path, "--user", "nobody", "--dry-run")

    def test_should_reject_missing_file(self):
        with self.assertRaises(CommandError):
            self._call(self.path + ".missing", "--user", self.user.username)

    def test_should_print_detected_layout(self):
        out = self._call(self.path, "--user", self.user.username, "--dry-run")
        self.assertIn("single HTML page (2025 layout)", out)

    def test_should_import_folder_export(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        write_folder(root, FOLDER_SAMPLE)
        out = self._call(root, "--user", self.user.username, "--dry-run")
        self.assertIn("folder of pages (2026 layout)", out)
        self.assertIn("Found 3 boards and 4 pins", out)
        self.assertIn("4 would be imported (2 public, 2 private)", out)

    def test_should_reject_unrelated_folder(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        with self.assertRaises(CommandError):
            self._call(root, "--user", self.user.username, "--dry-run")

    def test_should_reject_negative_delay(self):
        with self.assertRaises(CommandError):
            self._call(self.path, "--user", self.user.username,
                       "--delay", "-1")
