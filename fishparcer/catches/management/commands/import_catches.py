import json
from pathlib import Path

from django.core.management.base import BaseCommand

from fishparcer.catches.models import ApiSource
from fishparcer.catches.models import CatchRecord
from fishparcer.catches.services.parser import CatchParserService
from fishparcer.catches.services.photos import PhotoDownloadService


class Command(BaseCommand):
    help = "Import catch records from a JSON file (array or single object)."

    def add_arguments(self, parser):
        parser.add_argument("json_file", type=str, help="Path to JSON file")
        parser.add_argument(
            "--source-name",
            type=str,
            default="External API",
            help="API source name",
        )
        parser.add_argument(
            "--base-url",
            type=str,
            default="",
            help="Base URL for downloading photos",
        )
        parser.add_argument(
            "--download-photos",
            action="store_true",
            help="Download photos after import",
        )

    def handle(self, *args, **options):
        path = Path(options["json_file"])
        if not path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {path}"))
            return

        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        items = data if isinstance(data, list) else [data]

        source, _ = ApiSource.objects.get_or_create(
            name=options["source_name"],
            defaults={
                "base_url": options["base_url"],
            },
        )

        parser_service = CatchParserService(source=source)
        sync_log = parser_service.ingest_many(items)

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {sync_log.records_fetched} records "
                f"({sync_log.records_created} created, {sync_log.records_updated} updated)",
            ),
        )

        if options["download_photos"] and options["base_url"]:
            photo_service = PhotoDownloadService(base_url=options["base_url"])
            for catch in CatchRecord.objects.filter(source=source):
                stats = photo_service.download_for_catch(catch)
                self.stdout.write(f"  {catch.external_id}: {stats}")
