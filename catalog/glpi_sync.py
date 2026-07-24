from django.conf import settings
from django.utils import timezone
from .glpi import GlpiError, get_glpi_client
from .models import ExternalReference, GlpiCachedComputer, GlpiComputerSnapshot, ServerProfile


def snapshot_defaults_from_payload(payload):
    """Map one GLPI Computer payload to the stable per-reference snapshot."""
    from .glpi_cache import _snapshot_defaults
    return _snapshot_defaults(payload)


def snapshot_defaults_from_computer(computer):
    return {
        "external_name": computer.name or "", "inventory_number": computer.inventory_number or "", "serial_number": computer.serial_number or "", "external_uuid": computer.uuid or "",
        "external_status": computer.status or "", "manufacturer": computer.manufacturer or "", "model": computer.model or "", "external_type": computer.computer_type or "",
        "location": computer.location or "", "entity_name": computer.entity_name or "", "comment": computer.comment or "", "inventory_source": computer.inventory_source or "",
        "external_created_at": computer.created_at, "external_updated_at": computer.updated_at, "last_inventory_update": computer.last_inventory_update, "last_boot": computer.last_boot,
    }


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
    snapshot, _ = GlpiComputerSnapshot.objects.update_or_create(reference=reference, defaults=snapshot_defaults_from_computer(computer))
    reference.external_url = f"{settings.GLPI_BASE_URL}/front/computer.form.php?id={reference.external_id}"
    reference.last_synced_at = timezone.now()
    reference.last_sync_status = ExternalReference.SyncStatus.SUCCESS
    reference.last_sync_error = ""
    reference.save(update_fields=["external_url", "last_synced_at", "last_sync_status", "last_sync_error", "updated_at"])
    return snapshot


def refresh_linked_instances_from_cache(run):
    """Refresh every linked catalog object using cache rows, without N+1 queries."""
    references = list(ExternalReference.objects.filter(source_system=ExternalReference.SourceSystem.GLPI, external_object_type="Computer").select_related("instance"))
    by_external_id = {row.external_id: row for row in GlpiCachedComputer.objects.filter(external_id__in=[ref.external_id for ref in references], is_missing=False).prefetch_related("components")}
    matched = [ref for ref in references if ref.external_id in by_external_id]
    snapshots = {snapshot.reference_id: snapshot for snapshot in GlpiComputerSnapshot.objects.filter(reference_id__in=[ref.pk for ref in matched])}
    create, update = [], []
    now = timezone.now()
    for reference in matched:
        defaults = snapshot_defaults_from_payload(by_external_id[reference.external_id].raw_payload)
        snapshot = snapshots.get(reference.pk)
        if snapshot:
            for field, value in defaults.items(): setattr(snapshot, field, value)
            update.append(snapshot)
        else:
            create.append(GlpiComputerSnapshot(reference=reference, **defaults))
        reference.external_url = f"{settings.GLPI_BASE_URL}/front/computer.form.php?id={reference.external_id}"
        reference.last_synced_at, reference.last_sync_status, reference.last_sync_error = now, ExternalReference.SyncStatus.SUCCESS, ""
    if create: GlpiComputerSnapshot.objects.bulk_create(create, batch_size=500)
    if update:
        GlpiComputerSnapshot.objects.bulk_update(update, ["external_name", "inventory_number", "serial_number", "external_uuid", "external_status", "manufacturer", "model", "external_type", "location", "entity_name", "comment", "inventory_source", "external_created_at", "external_updated_at", "last_inventory_update", "last_boot", "updated_at"], batch_size=500)
    if matched:
        ExternalReference.objects.bulk_update(matched, ["external_url", "last_synced_at", "last_sync_status", "last_sync_error", "updated_at"], batch_size=500)

    profiles = {profile.instance_id: profile for profile in ServerProfile.objects.filter(instance_id__in=[ref.instance_id for ref in matched])}
    profile_updates = []
    for reference in matched:
        profile = profiles.get(reference.instance_id)
        if not profile or not profile.glpi_managed_fields:
            continue
        payloads = {"computer": by_external_id[reference.external_id].raw_payload}
        for component in by_external_id[reference.external_id].components.all():
            payloads[component.component_key] = component.payload
        from .glpi_import import normalize_import_candidates
        candidates = normalize_import_candidates(payloads)
        changed = False
        for field in profile.glpi_managed_fields:
            if field in candidates:
                value = candidates[field][0]
                try: value = {"core_count": int}.get(field, str)(value)
                except (TypeError, ValueError): continue
                setattr(profile, field, value); changed = True
        if changed: profile_updates.append(profile)
    if profile_updates:
        ServerProfile.objects.bulk_update(profile_updates, ["manufacturer", "model", "cpu_summary", "core_count", "memory_total_gb", "storage_summary", "raid_controller", "hypervisor", "updated_at"], batch_size=500)
    return {"linked_references_updated": len(matched), "linked_snapshots_created": len(create), "linked_profiles_updated": len(profile_updates)}
