"""Local GLPI cache and bulk synchronization services."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from typing import Any, Iterable

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .glpi import GlpiError, get_glpi_client, normalize_computer
from .glpi_database import GlpiDatabaseDisabled, GlpiDatabaseError, get_glpi_database_client
from .glpi_import import COMPONENT_COLLECTORS, RELATED_COLLECTORS, normalize_import_candidates
from .models import (
    ExternalReference,
    GlpiCacheSyncRun,
    GlpiCachedComponent,
    GlpiCachedComputer,
    GlpiCachedLookup,
    GlpiComputerSnapshot,
    Instance,
    InstanceType,
    Service,
    ServiceMembership,
)


LOOKUPS = (
    (GlpiCachedLookup.Kind.COMPUTER_TYPE, "ComputerType"),
    (GlpiCachedLookup.Kind.STATE, "State"),
    (GlpiCachedLookup.Kind.LOCATION, "Location"),
    (GlpiCachedLookup.Kind.MANUFACTURER, "Manufacturer"),
    (GlpiCachedLookup.Kind.COMPUTER_MODEL, "ComputerModel"),
    (GlpiCachedLookup.Kind.AUTO_UPDATE_SYSTEM, "AutoUpdateSystem"),
)
COMPONENT_KEYS = COMPONENT_COLLECTORS + RELATED_COLLECTORS
DB_FALLBACK_COMPONENTS = {"processor"}


def _pages(fetch_page, page_size: int) -> list[dict[str, Any]]:
    result = []
    start = 0
    while True:
        page = fetch_page(start=start, limit=page_size)
        result.extend(page)
        if len(page) < page_size:
            return result
        start += page_size


def _component_payloads(computer_id: str) -> tuple[str, dict[str, list[dict[str, Any]]], dict[str, str]]:
    client = get_glpi_client()
    payloads: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    for key in COMPONENT_COLLECTORS:
        try:
            payloads[key] = client.get_computer_component_payload(computer_id, key)
        except GlpiError as exc:
            errors[key] = str(exc)
    for key in RELATED_COLLECTORS:
        try:
            payloads[key] = client.get_computer_related_payload(computer_id, key)
        except GlpiError as exc:
            errors[key] = str(exc)
    return computer_id, payloads, errors


def _lookup_id(value: Any, kind: str, lookup_ids: dict[tuple[str, str], int]) -> int | None:
    if not isinstance(value, dict) or value.get("id") in (None, ""):
        return None
    return lookup_ids.get((kind, str(value["id"])))


def _snapshot_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    computer = normalize_computer(payload)
    return {
        "external_name": computer.name or "",
        "inventory_number": computer.inventory_number or "",
        "serial_number": computer.serial_number or "",
        "external_uuid": computer.uuid or "",
        "external_status": computer.status or "",
        "manufacturer": computer.manufacturer or "",
        "model": computer.model or "",
        "external_type": computer.computer_type or "",
        "location": computer.location or "",
        "entity_name": computer.entity_name or "",
        "comment": computer.comment or "",
        "inventory_source": computer.inventory_source or "",
        "external_created_at": computer.created_at,
        "external_updated_at": computer.updated_at,
        "last_inventory_update": computer.last_inventory_update,
        "last_boot": computer.last_boot,
    }


def _upsert_lookups(run, values: dict[str, list[dict[str, Any]]]) -> dict[tuple[str, str], int]:
    existing = {(item.kind, item.external_id): item for item in GlpiCachedLookup.objects.all()}
    create, update = [], []
    successful_kinds = set(values)
    for kind, rows in values.items():
        for row in rows:
            external_id = str(row.get("id", ""))
            if not external_id:
                continue
            item = existing.get((kind, external_id))
            defaults = {"name": str(row.get("name") or ""), "complete_name": str(row.get("completename") or ""), "raw_payload": row, "last_seen_run": run, "is_missing": False}
            if item:
                for field, value in defaults.items():
                    setattr(item, field, value)
                update.append(item)
            else:
                create.append(GlpiCachedLookup(kind=kind, external_id=external_id, **defaults))
    if create:
        GlpiCachedLookup.objects.bulk_create(create, batch_size=500)
    if update:
        GlpiCachedLookup.objects.bulk_update(update, ["name", "complete_name", "raw_payload", "last_seen_run", "is_missing", "updated_at"], batch_size=500)
    for kind in successful_kinds:
        GlpiCachedLookup.objects.filter(kind=kind).exclude(last_seen_run=run).update(is_missing=True)
    return {(item.kind, item.external_id): item.pk for item in GlpiCachedLookup.objects.all()}


def _persist_cache(run, computers: list[dict[str, Any]], lookups: dict[str, list[dict[str, Any]]], component_data, component_errors) -> dict[str, int]:
    now = timezone.now()
    with transaction.atomic():
        lookup_ids = _upsert_lookups(run, lookups)
        existing = {item.external_id: item for item in GlpiCachedComputer.objects.all()}
        create, update = [], []
        for payload in computers:
            external_id = str(payload["id"])
            item = existing.get(external_id)
            defaults = {
                "name": str(payload.get("name") or ""), "comment": str(payload.get("comment") or ""),
                "serial_number": str(payload.get("serial") or ""), "inventory_number": str(payload.get("otherserial") or ""),
                "external_uuid": str(payload.get("uuid") or ""), "computer_type_id": _lookup_id(payload.get("type"), GlpiCachedLookup.Kind.COMPUTER_TYPE, lookup_ids),
                "state_id": _lookup_id(payload.get("status"), GlpiCachedLookup.Kind.STATE, lookup_ids), "location_id": _lookup_id(payload.get("location"), GlpiCachedLookup.Kind.LOCATION, lookup_ids),
                "manufacturer_id": _lookup_id(payload.get("manufacturer"), GlpiCachedLookup.Kind.MANUFACTURER, lookup_ids), "model_id": _lookup_id(payload.get("model"), GlpiCachedLookup.Kind.COMPUTER_MODEL, lookup_ids),
                "auto_update_system_id": _lookup_id(payload.get("autoupdatesystem"), GlpiCachedLookup.Kind.AUTO_UPDATE_SYSTEM, lookup_ids),
                "external_created_at": normalize_computer(payload).created_at, "external_updated_at": normalize_computer(payload).updated_at,
                "last_inventory_update": normalize_computer(payload).last_inventory_update, "last_boot": normalize_computer(payload).last_boot,
                "raw_payload": payload, "last_seen_run": run, "last_successful_sync_at": now, "is_missing": False, "last_error": "",
            }
            if item:
                for field, value in defaults.items(): setattr(item, field, value)
                update.append(item)
            else:
                create.append(GlpiCachedComputer(external_id=external_id, **defaults))
        if create: GlpiCachedComputer.objects.bulk_create(create, batch_size=500)
        computer_fields = ["name", "comment", "serial_number", "inventory_number", "external_uuid", "computer_type", "state", "location", "manufacturer", "model", "auto_update_system", "external_created_at", "external_updated_at", "last_inventory_update", "last_boot", "raw_payload", "last_seen_run", "last_successful_sync_at", "is_missing", "last_error", "updated_at"]
        if update: GlpiCachedComputer.objects.bulk_update(update, computer_fields, batch_size=500)
        GlpiCachedComputer.objects.exclude(last_seen_run=run).update(is_missing=True)

        cached = {item.external_id: item for item in GlpiCachedComputer.objects.all()}
        existing_components = {(item.computer_id, item.component_key): item for item in GlpiCachedComponent.objects.all()}
        component_create, component_update = [], []
        for external_id, payloads in component_data.items():
            computer = cached[external_id]
            for key, result in payloads.items():
                item = existing_components.get((computer.pk, key))
                source, payload = result["source"], result["payload"]
                normalized = normalize_import_candidates({"computer": computer.raw_payload, key: payload}, processor_source=source)
                defaults = {"payload": payload, "normalized_payload": {field: value[0] for field, value in normalized.items()}, "source": source, "last_attempt_at": now, "last_successful_sync_at": now, "last_error": ""}
                if item:
                    for field, value in defaults.items(): setattr(item, field, value)
                    component_update.append(item)
                else: component_create.append(GlpiCachedComponent(computer=computer, component_key=key, **defaults))
            for key, error in component_errors.get(external_id, {}).items():
                item = existing_components.get((computer.pk, key))
                if item:
                    item.last_attempt_at, item.last_error = now, error[:500]
                    component_update.append(item)
                else: component_create.append(GlpiCachedComponent(computer=computer, component_key=key, last_attempt_at=now, last_error=error[:500]))
        if component_create: GlpiCachedComponent.objects.bulk_create(component_create, batch_size=500)
        if component_update: GlpiCachedComponent.objects.bulk_update(component_update, ["payload", "normalized_payload", "source", "last_attempt_at", "last_successful_sync_at", "last_error", "updated_at"], batch_size=500)
    return {"cache_computers_created": len(create), "cache_computers_updated": len(update), "cache_computers_missing": GlpiCachedComputer.objects.filter(is_missing=True).count()}


def sync_glpi_cache(*, requested_by=None, trigger=GlpiCacheSyncRun.Trigger.MANUAL, page_size: int | None = None, component_workers: int | None = None, refresh_linked: bool = True) -> GlpiCacheSyncRun:
    run = GlpiCacheSyncRun.objects.create(trigger=trigger, requested_by=requested_by, started_at=timezone.now())
    page_size = page_size or settings.GLPI_API_PAGE_SIZE
    workers = component_workers or settings.GLPI_COMPONENT_WORKERS
    client = get_glpi_client()
    stats: dict[str, Any] = defaultdict(int)
    errors: list[str] = []
    try:
        computers = _pages(client.list_computers, page_size)
    except GlpiError as exc:
        run.status, run.finished_at, run.error_summary = GlpiCacheSyncRun.Status.FAILED, timezone.now(), str(exc)[:2000]
        run.statistics = {"computers_received": 0}
        run.save(update_fields=["status", "finished_at", "error_summary", "statistics", "updated_at"])
        return run
    run.full_computer_list_received = True
    stats["computers_received"] = len(computers)
    lookups = {}
    for kind, resource in LOOKUPS:
        try: lookups[kind] = _pages(lambda **kwargs: client.list_dropdown(resource, **kwargs), page_size)
        except GlpiError as exc:
            errors.append(f"{resource}: {exc}")

    component_data, component_errors, api_empty_processors = defaultdict(dict), defaultdict(dict), []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_component_payloads, str(payload["id"])) for payload in computers]
        for future in as_completed(futures):
            external_id, payloads, item_errors = future.result()
            if item_errors:
                component_errors[external_id].update(item_errors)
            for key, payload in payloads.items():
                component_data[external_id][key] = {"payload": payload, "source": GlpiCachedComponent.Source.API}
                if key == "processor" and not payload: api_empty_processors.append(external_id)
    if api_empty_processors:
        try:
            db_rows = get_glpi_database_client().get_computer_processors_many(api_empty_processors)
        except GlpiDatabaseDisabled:
            db_rows = {}
        except GlpiDatabaseError as exc:
            for external_id in api_empty_processors:
                # A failed fallback is not a valid empty component list: retain
                # the last successful processor payload in the local cache.
                component_data[external_id].pop("processor", None)
                component_errors[external_id]["processor_db"] = str(exc)
        else:
            for external_id, rows in db_rows.items():
                if rows:
                    component_data[external_id]["processor"] = {"payload": rows, "source": GlpiCachedComponent.Source.DATABASE}
                    stats["processor_db_fallbacks"] += 1
    stats["component_errors"] = sum(len(value) for value in component_errors.values())
    try:
        stats.update(_persist_cache(run, computers, lookups, component_data, component_errors))
        if refresh_linked:
            from .glpi_sync import refresh_linked_instances_from_cache
            stats.update(refresh_linked_instances_from_cache(run))
        run.status = GlpiCacheSyncRun.Status.PARTIAL if errors or component_errors else GlpiCacheSyncRun.Status.COMPLETED
        run.error_summary = "\n".join((errors + [f"components: {stats['component_errors']}"] if component_errors else errors))[:2000]
    except Exception as exc:
        run.status, run.error_summary = GlpiCacheSyncRun.Status.FAILED, f"Ошибка сохранения кэша: {type(exc).__name__}."
    run.finished_at, run.statistics = timezone.now(), dict(stats)
    run.save(update_fields=["status", "finished_at", "full_computer_list_received", "statistics", "error_summary", "updated_at"])
    return run


@transaction.atomic
def create_instances_from_glpi_cache(cached_computer_ids: Iterable[int], *, instance_type: InstanceType, service: Service | None = None, user=None) -> dict[str, int]:
    selected = list(GlpiCachedComputer.objects.select_for_update().filter(pk__in=set(cached_computer_ids), is_missing=False).exclude(name=""))
    references = set(ExternalReference.objects.filter(source_system=ExternalReference.SourceSystem.GLPI, external_object_type="Computer", external_id__in=[row.external_id for row in selected]).values_list("external_id", flat=True))
    create_rows = [row for row in selected if row.external_id not in references]
    instances = [Instance(name=row.name, instance_type=instance_type, status=Instance.Status.ACTIVE) for row in create_rows]
    Instance.objects.bulk_create(instances, batch_size=500)
    for instance in instances: instance.catalog_code = f"INS-{instance.pk:06d}"
    if instances: Instance.objects.bulk_update(instances, ["catalog_code"], batch_size=500)
    refs = [ExternalReference(instance=instance, source_system=ExternalReference.SourceSystem.GLPI, external_object_type="Computer", external_id=row.external_id) for instance, row in zip(instances, create_rows)]
    if refs: ExternalReference.objects.bulk_create(refs, batch_size=500)
    if refs:
        GlpiComputerSnapshot.objects.bulk_create([GlpiComputerSnapshot(reference=ref, **_snapshot_defaults(row.raw_payload)) for ref, row in zip(refs, create_rows)], batch_size=500)
    if service and instances:
        ServiceMembership.objects.bulk_create([ServiceMembership(service=service, instance=instance, created_by=user, updated_by=user) for instance in instances], batch_size=500)
    return {"selected": len(selected), "created": len(instances), "already_linked": len(selected) - len(create_rows), "skipped_missing_or_unnamed": len(set(cached_computer_ids)) - len(selected), "memberships_created": len(instances) if service else 0}
