from django.core.management.base import BaseCommand, CommandError
from catalog.glpi import GlpiError
from catalog.glpi_sync import sync_glpi_reference
from catalog.models import Instance


class Command(BaseCommand):
    help = "Synchronize one catalog instance from its GLPI Computer reference."

    def add_arguments(self, parser):
        parser.add_argument("catalog_code")

    def handle(self, *args, **options):
        try:
            instance = Instance.objects.get(catalog_code=options["catalog_code"])
        except Instance.DoesNotExist as exc:
            raise CommandError("Экземпляр с указанным системным кодом не найден.") from exc
        reference = instance.external_references.filter(source_system="glpi", external_object_type="Computer").order_by("pk").first()
        if not reference:
            raise CommandError("Для экземпляра не задана ссылка GLPI Computer.")
        try:
            snapshot = sync_glpi_reference(reference)
        except GlpiError as exc:
            raise CommandError(f"Синхронизация GLPI не выполнена: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"GLPI Computer {reference.external_id} синхронизирован: {snapshot.external_name or 'без имени'}"))
