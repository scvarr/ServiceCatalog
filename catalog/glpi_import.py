from collections import Counter
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .glpi import GlpiError, get_glpi_client
from .models import GlpiImportCandidate, GlpiImportPayload, GlpiImportSession, ServerProfile


PROFILE_FIELDS = {
    "manufacturer": str,
    "model": str,
    "cpu_summary": str,
    "core_count": int,
    "memory_total_gb": Decimal,
    "storage_summary": str,
    "raid_controller": str,
    "hypervisor": str,
}
COMPONENT_COLLECTORS = ("processor", "memory", "controller", "hard_drive", "network_card")
RELATED_COLLECTORS = ("os_installation", "volume", "virtual_machine")


def _nested_name(value):
    return value.get("name") if isinstance(value, dict) else str(value or "")


def _number(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _display_decimal(value):
    return format(value.normalize(), "f") if value else ""


def _grouped(values):
    counts = Counter(value for value in values if value)
    return ", ".join(f"{count} × {value}" if count > 1 else value for value, count in counts.items())


def _mb_to_gb(value):
    return (_number(value) / Decimal(1024)).quantize(Decimal("0.01"))


def normalize_import_candidates(payloads):
    """Return {profile_field: (value, source, normalization_rule)}."""
    computer = payloads.get("computer", {})
    candidates = {}
    for field in ("manufacturer", "model"):
        value = _nested_name(computer.get(field))
        if value:
            candidates[field] = (value, "computer", "nested_name")

    processors = payloads.get("processor", [])
    processor_names = [_nested_name(row.get("processor")) for row in processors]
    cpu_summary = _grouped(processor_names)
    if cpu_summary:
        candidates["cpu_summary"] = (cpu_summary, "processor", "grouped_names")
    core_count = sum(int(_number(row.get("nbcores"))) for row in processors if _number(row.get("nbcores")) > 0)
    if core_count:
        candidates["core_count"] = (str(core_count), "processor", "sum_nbcores")

    memory_mb = sum((_number(row.get("size")) for row in payloads.get("memory", [])), Decimal(0))
    if memory_mb:
        candidates["memory_total_gb"] = (_display_decimal(_mb_to_gb(memory_mb)), "memory", "sum_size_mb_to_gb")

    controllers = _grouped(_nested_name(row.get("controller")) for row in payloads.get("controller", []))
    if controllers:
        candidates["raid_controller"] = (controllers, "controller", "grouped_names")

    drives = []
    for row in payloads.get("hard_drive", []):
        name = _nested_name(row.get("hard_drive"))
        capacity = _display_decimal(_mb_to_gb(row.get("capacity")))
        if name:
            drives.append(f"{name} — {capacity} ГБ" if capacity else name)
    storage = _grouped(drives)
    if storage:
        candidates["storage_summary"] = (storage, "hard_drive", "grouped_drive_capacity_mb_to_gb")

    installations = payloads.get("os_installation", [])
    if installations:
        row = installations[0]
        parts = [_nested_name(row.get(key)) for key in ("operatingsystem", "version", "edition", "architecture", "kernel_version")]
        os_summary = " ".join(part for part in parts if part)
        if os_summary:
            candidates["hypervisor"] = (os_summary, "os_installation", "first_os_installation")
    return candidates


@transaction.atomic
def create_glpi_import(reference, user=None):
    session = GlpiImportSession.objects.create(
        instance=reference.instance,
        reference=reference,
        requested_by=user,
        status=GlpiImportSession.Status.RUNNING,
        started_at=timezone.now(),
        normalizer_version="v2",
    )
    client = get_glpi_client()
    payloads = {}
    failures = []
    collectors = [("computer", lambda: client.get_computer_payload(reference.external_id))]
    collectors += [(key, lambda key=key: client.get_computer_component_payload(reference.external_id, key)) for key in COMPONENT_COLLECTORS]
    collectors += [(key, lambda key=key: client.get_computer_related_payload(reference.external_id, key)) for key in RELATED_COLLECTORS]
    for key, collect in collectors:
        try:
            payload = collect()
            payloads[key] = payload
            GlpiImportPayload.objects.create(session=session, endpoint_key=key, http_status=200, payload=payload)
        except GlpiError as exc:
            failures.append(key)
            GlpiImportPayload.objects.create(session=session, endpoint_key=key, http_status=exc.http_status, error=str(exc)[:500])

    if "computer" not in payloads:
        session.status = GlpiImportSession.Status.FAILED
        session.error = "Не получен основной объект Computer."
    else:
        profile, _ = ServerProfile.objects.get_or_create(instance=reference.instance)
        for field_key, (proposed_value, source, rule) in normalize_import_candidates(payloads).items():
            current_value = getattr(profile, field_key, "") or ""
            GlpiImportCandidate.objects.create(
                session=session,
                field_key=field_key,
                current_value=str(current_value),
                proposed_value=str(proposed_value),
                source=source,
                rule=rule,
            )
        session.status = GlpiImportSession.Status.PARTIAL if failures else GlpiImportSession.Status.COMPLETED
        if failures:
            session.error = f"Не получены: {', '.join(failures)}."
    session.finished_at = timezone.now()
    session.save(update_fields=["status", "error", "finished_at", "normalizer_version", "updated_at"])
    return session


@transaction.atomic
def apply_glpi_candidates(session, candidate_ids, user):
    profile, _ = ServerProfile.objects.get_or_create(instance=session.instance)
    for candidate in session.candidates.filter(pk__in=candidate_ids, decision=GlpiImportCandidate.Decision.PENDING):
        converter = PROFILE_FIELDS.get(candidate.field_key)
        if not converter:
            continue
        try:
            value = converter(candidate.proposed_value)
        except (InvalidOperation, TypeError, ValueError):
            continue
        setattr(profile, candidate.field_key, value)
        candidate.decision = GlpiImportCandidate.Decision.APPLIED
        candidate.applied_at = timezone.now()
        candidate.applied_by = user
        candidate.save(update_fields=["decision", "applied_at", "applied_by", "updated_at"])
    profile.save()
