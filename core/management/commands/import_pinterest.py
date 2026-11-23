from django.core.management import BaseCommand, CommandError

from core.importers.importer import PinImporter
from core.importers.pinterest import (
    ExportFormatError, import_items, read_export,
)
from users.models import User


def _pin_link(source_id):
    """The Pinterest page of an imported pin, for checking it by hand."""
    prefix = "pinterest:"
    if source_id.startswith(prefix):
        return "https://www.pinterest.com/pin/%s/" % source_id[len(prefix):]
    return source_id


class Command(BaseCommand):
    help = (
        "Import boards and pins from a Pinterest data export (from Settings "
        "> Privacy and data > Request your data): the HTML file of older "
        "exports, or the folder or .zip of newer ones. Images are "
        "downloaded from Pinterest's image server. Pins imported before are "
        "skipped, so an interrupted import can be run again."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "export",
            help="Path to the export: its HTML file (older exports), or its "
                 "folder, .zip or any page in the folder (newer exports).",
        )
        parser.add_argument(
            "--user", required=True,
            help="Username of the Pinry user who will own the pins.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Count what would be imported without changing anything "
                 "or downloading images.",
        )
        parser.add_argument(
            "--private", action="store_true",
            help="Make every imported board and pin private, whatever its "
                 "privacy on Pinterest.",
        )
        parser.add_argument(
            "--tag", action="append", default=[], metavar="TAG",
            help="Add TAG to every imported pin. Can be given more than "
                 "once.",
        )
        parser.add_argument(
            "--delay", type=float, default=1.0, metavar="SECONDS",
            help="Pause before each image download (default 1).",
        )

    def handle(self, *args, export, user, dry_run, private, tag, delay,
               **options):
        if delay < 0:
            raise CommandError("--delay can't be negative.")
        try:
            owner = User.objects.get(username=user)
        except User.DoesNotExist:
            raise CommandError("No user named %r." % user) from None
        try:
            parser, boards, pins = read_export(export)
        except OSError as e:
            raise CommandError("Can't read %s: %s" % (export, e)) from e
        except ExportFormatError as e:
            raise CommandError(str(e)) from e
        boards, pins = import_items(boards, pins)

        self.stdout.write("Export layout: %s." % parser.label)
        self.stdout.write(
            "Found %d boards and %d pins in the export."
            % (len(boards), len(pins))
        )
        importer = PinImporter(
            owner,
            force_private=private,
            tags=[t.strip() for t in tag if t.strip()],
            delay=delay,
            dry_run=dry_run,
            progress=self.stdout.write,
        )
        report = importer.run(boards, pins)

        verb = "would be" if dry_run else "were"
        self.stdout.write(
            "Boards: %d %s created, %d already existed."
            % (report.boards_created, verb, report.boards_existing)
        )
        if report.boards_made_private:
            self.stdout.write(
                "%d existing boards %s made private to match Pinterest."
                % (report.boards_made_private, verb)
            )
        self.stdout.write(
            "Pins: %d %s imported (%d public, %d private), %d were imported "
            "before."
            % (report.pins_imported, verb, report.pins_public,
               report.pins_private, report.pins_already_imported)
        )
        if report.gone:
            self.stdout.write(
                "%d pins no longer exist on Pinterest (no copy of their "
                "image is left), so they can't be imported:"
                % len(report.gone)
            )
            for source_id, _reason in report.gone:
                self.stdout.write("  %s" % _pin_link(source_id))
        if report.failed:
            self.stdout.write(
                "%d pins failed; run the import again to retry them."
                % len(report.failed)
            )
            for source_id, reason in report.failed:
                self.stdout.write("  %s: %s" % (_pin_link(source_id), reason))
        if dry_run:
            self.stdout.write("Dry run: nothing was changed.")
