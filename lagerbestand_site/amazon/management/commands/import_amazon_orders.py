from django.core.management.base import BaseCommand, CommandError

from amazon.importer import AmazonOrderImporter


class Command(BaseCommand):
    help = 'Importiert Amazon-Bestellungen über die Selling Partner API.'

    def handle(self, *args, **options):
        importer = AmazonOrderImporter()
        try:
            created = importer.import_orders()
            self.stdout.write(self.style.SUCCESS(f'Import abgeschlossen: {created} neue Bestellungen.'))
        except KeyError as exc:
            importer.logger.log(f'Import fehlgeschlagen || Fehlende Umgebungsvariable {exc}')
            raise CommandError(f'Fehlende ENV Variable: {exc}') from exc
        except Exception as exc:  # noqa: BLE001
            importer.logger.log(f'Import fehlgeschlagen || {exc}')
            raise CommandError(str(exc)) from exc
