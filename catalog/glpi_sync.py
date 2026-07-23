from django.conf import settings
from django.utils import timezone
from .glpi import GlpiError, get_glpi_client
from .models import ExternalReference, GlpiComputerSnapshot


def sync_glpi_reference(reference: ExternalReference):
    if reference.source_system != ExternalReference.SourceSystem.GLPI or reference.external_object_type != "Computer":
        raise GlpiError("Для экземпляра не задана ссылка на объект GLPI Computer.")
    try:
        computer = get_glpi_client().get_computer(reference.external_id)
    except GlpiError as exc:
        reference.last_sync_status = ExternalReference.SyncStatus.ERROR
        reference.last_sync_error = str(exc)[:500]
        reference.save(update_fields=["last_sync_status", "last_sync_error", "updated_at"])
        raise
    snapshot, _ = GlpiComputerSnapshot.objects.update_or_create(
        reference=reference,
        defaults={
            "external_name": computer.name or "", "inventory_number": computer.inventory_number or "",
            "serial_number": computer.serial_number or "", "external_uuid": computer.uuid or "",
            "external_status": computer.status or "", "manufacturer": computer.manufacturer or "", "model": computer.model or "",
            "external_type": computer.computer_type or "", "location": computer.location or "", "entity_name": computer.entity_name or "",
            "comment": computer.comment or "", "inventory_source": computer.inventory_source or "", "external_created_at": computer.created_at,
            "external_updated_at": computer.updated_at, "last_inventory_update": computer.last_inventory_update, "last_boot": computer.last_boot,
        },
    )
    reference.external_url = f"{settings.GLPI_BASE_URL}/front/computer.form.php?id={reference.external_id}"
    reference.last_synced_at = timezone.now()
    reference.last_sync_status = ExternalReference.SyncStatus.SUCCESS
    reference.last_sync_error = ""
    reference.save(update_fields=["external_url", "last_synced_at", "last_sync_status", "last_sync_error", "updated_at"])
    return snapshot
