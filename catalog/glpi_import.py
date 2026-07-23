from django.db import transaction
from django.utils import timezone

from .glpi import GlpiError, get_glpi_client
from .models import GlpiImportCandidate, GlpiImportPayload, GlpiImportSession, ServerProfile


PROFILE_FIELDS = {
    "manufacturer": ("manufacturer", "direct"),
    "model": ("model", "direct"),
}


def _nested_name(value):
    return value.get("name") if isinstance(value, dict) else ""


def normalize_computer_candidates(payload):
    return {
        "manufacturer": _nested_name(payload.get("manufacturer")),
        "model": _nested_name(payload.get("model")),
    }


@transaction.atomic
def create_glpi_import(reference, user=None):
    session = GlpiImportSession.objects.create(instance=reference.instance, reference=reference, requested_by=user, status=GlpiImportSession.Status.RUNNING, started_at=timezone.now())
    try:
        payload = get_glpi_client().get_computer_payload(reference.external_id)
        GlpiImportPayload.objects.create(session=session, endpoint_key="computer", http_status=200, payload=payload)
        profile, _ = ServerProfile.objects.get_or_create(instance=reference.instance)
        for field_key, proposed_value in normalize_computer_candidates(payload).items():
            current_value = getattr(profile, field_key, "") or ""
            GlpiImportCandidate.objects.create(session=session, field_key=field_key, current_value=str(current_value), proposed_value=str(proposed_value or ""), rule="direct")
        session.status = GlpiImportSession.Status.COMPLETED
    except GlpiError as exc:
        session.status = GlpiImportSession.Status.FAILED
        session.error = str(exc)[:500]
    session.finished_at = timezone.now()
    session.save(update_fields=["status", "error", "finished_at", "updated_at"])
    return session


@transaction.atomic
def apply_glpi_candidates(session, candidate_ids, user):
    profile, _ = ServerProfile.objects.get_or_create(instance=session.instance)
    allowed = set(PROFILE_FIELDS)
    for candidate in session.candidates.filter(pk__in=candidate_ids, decision=GlpiImportCandidate.Decision.PENDING):
        if candidate.field_key not in allowed:
            continue
        setattr(profile, candidate.field_key, candidate.proposed_value)
        candidate.decision = GlpiImportCandidate.Decision.APPLIED
        candidate.applied_at = timezone.now(); candidate.applied_by = user
        candidate.save(update_fields=["decision", "applied_at", "applied_by", "updated_at"])
    profile.save()
