from django.core.management.base import BaseCommand

from fishparcer.catches.services.fetcher import CatchFetchService


class Command(BaseCommand):
    help = "Загрузить JSON по URL и сохранить записи в базу данных."

    def add_arguments(self, parser):
        parser.add_argument("url", type=str, help="URL API, который возвращает JSON")
        parser.add_argument(
            "--source-name",
            type=str,
            default="",
            help="Имя источника (по умолчанию — домен из URL)",
        )
        parser.add_argument(
            "--download-photos",
            action="store_true",
            help="Скачать фото после импорта",
        )
        parser.add_argument(
            "--header",
            action="append",
            default=[],
            help="HTTP-заголовок в формате 'Key: Value' (можно указать несколько раз)",
        )

    def handle(self, *args, **options):
        headers = self._parse_headers(options["header"])
        service = CatchFetchService()

        try:
            sync_log, photo_stats = service.import_from_url(
                options["url"],
                source_name=options["source_name"],
                download_photos=options["download_photos"],
                headers=headers,
            )
        except Exception as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Загружено {sync_log.records_fetched} записей "
                f"({sync_log.records_created} новых, {sync_log.records_updated} обновлено)",
            ),
        )

        if photo_stats:
            for external_id, stats in photo_stats.items():
                self.stdout.write(f"  {external_id}: {stats}")

    @staticmethod
    def _parse_headers(raw_headers: list[str]) -> dict[str, str]:
        headers: dict[str, str] = {}
        for header in raw_headers:
            if ":" not in header:
                msg = f"Неверный формат заголовка: {header}. Используйте 'Key: Value'"
                raise ValueError(msg)
            key, value = header.split(":", 1)
            headers[key.strip()] = value.strip()
        return headers
