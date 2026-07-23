import csv
import hashlib
import io
from collections import Counter, defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch

from catalog.models import ActualServiceMetric, ExternalReference, Instance, Service, ServiceMembership, ServiceMetricCategory
from .models import (
    Contract,
    ContractActualSnapshot,
    ContractActualSnapshotInstance,
    ContractActualSnapshotService,
    ContractListImport,
    ContractServiceTerm,
    NamedContractPosition,
)


STATUS_LABELS = {
    "match": "Совпадает",
    "within_tolerance": "В пределах допуска",
    "exceeded": "Превышение допуска",
    "shortfall": "Недостаток относительно договора",
    "composition_changed": "Состав изменён",
    "incomplete": "Данные неполные",
    "missing_term": "Нет договорной позиции",
}


def _allowed_delta(term):
    if term.contracted_quantity is None:
        return None
    if term.tolerance_type == ContractServiceTerm.ToleranceType.PERCENT:
        return Decimal(term.contracted_quantity) * term.tolerance_value / Decimal("100")
    return term.tolerance_value


def actual_metric_for_category(category, active_instance_ids=None):
    if not category:
        return None, None, None
    if category.actual_value_method == "member_count":
        return Decimal(len(active_instance_ids or ())), "calculated", None
    metric = category.actual_metrics.order_by("-effective_at", "-created_at").first()
    if not metric:
        return None, None, None
    return metric.value, metric.source, metric.effective_at


def _comparison_result(term, actual_ids, positions, include_details):
    actual_ids = set(actual_ids)
    active_count = len(actual_ids)
    actual_value, actual_source, actual_at = actual_metric_for_category(term.metric_category, actual_ids)
    if actual_value is None and not term.metric_category_id:
        actual_value, actual_source = Decimal(active_count), "calculated"
    mode = term.accounting_mode
    named_required = mode in {ContractServiceTerm.AccountingMode.NAMED, ContractServiceTerm.AccountingMode.MIXED}
    quantitative_required = mode in {ContractServiceTerm.AccountingMode.QUANTITATIVE, ContractServiceTerm.AccountingMode.MIXED}
    positions = [position for position in positions if position.match_status != NamedContractPosition.MatchStatus.IGNORED]
    matched_positions = [position for position in positions if position.match_status == NamedContractPosition.MatchStatus.MATCHED and position.instance_id]
    matched_ids = {position.instance_id for position in matched_positions}
    added_ids = actual_ids - matched_ids
    missing_positions = [position for position in matched_positions if position.instance_id not in actual_ids]
    unresolved = [position for position in positions if position.match_status in {NamedContractPosition.MatchStatus.UNMATCHED, NamedContractPosition.MatchStatus.AMBIGUOUS}]
    incomplete = (quantitative_required and (term.contracted_quantity is None or actual_value is None)) or (named_required and (not positions or unresolved))
    quantity_delta = actual_value - term.contracted_quantity if quantitative_required and term.contracted_quantity is not None and actual_value is not None else None
    allowed_delta = _allowed_delta(term) if quantitative_required else None
    composition_changed = named_required and bool(added_ids or missing_positions)

    if incomplete:
        status = "incomplete"
    elif quantitative_required and quantity_delta > allowed_delta:
        status = "exceeded"
    elif quantitative_required and quantity_delta < 0:
        status = "shortfall"
    elif composition_changed:
        status = "composition_changed"
    elif quantitative_required and quantity_delta > 0:
        status = "within_tolerance"
    else:
        status = "match"

    result = {
        "term": term,
        "service": term.service,
        "mode": mode,
        "contract_quantity": term.contracted_quantity if quantitative_required else len(positions),
        "actual_quantity": actual_value if quantitative_required else active_count,
        "actual_source": actual_source,
        "actual_at": actual_at,
        "unit": term.unit or (term.metric_category.unit if term.metric_category_id else None),
        "quantity_delta": quantity_delta,
        "allowed_delta": allowed_delta,
        "percent_delta": None if not quantitative_required or not term.contracted_quantity or quantity_delta is None else Decimal(quantity_delta) * Decimal("100") / Decimal(term.contracted_quantity),
        "status": status,
        "status_label": STATUS_LABELS[status],
        "composition_changed": composition_changed,
        "composition_delta": f"+{len(added_ids)} / −{len(missing_positions)}" if named_required else "—",
        "matched_count": len(actual_ids & matched_ids),
        "added_count": len(added_ids),
        "missing_count": len(missing_positions),
        "unresolved_count": len(unresolved),
        "incomplete": incomplete,
    }
    if include_details:
        result.update(
            {
                "matched": [position for position in matched_positions if position.instance_id in actual_ids],
                "contract_only": missing_positions,
                "actual_only": Instance.objects.filter(pk__in=added_ids).select_related("instance_type").order_by("name"),
                "unmatched": [position for position in unresolved if position.match_status == NamedContractPosition.MatchStatus.UNMATCHED],
                "ambiguous": [position for position in unresolved if position.match_status == NamedContractPosition.MatchStatus.AMBIGUOUS],
                "upper_limit": term.allowed_upper_limit,
            }
        )
    return result


def compare_contract_service_to_actual(term, *, include_details=False, actual_ids=None, positions=None):
    if actual_ids is None:
        actual_ids = term.service.memberships.filter(status=ServiceMembership.Status.ACTIVE).values_list("instance_id", flat=True)
    if positions is None:
        positions = list(term.named_positions.all()) if term.accounting_mode in {"named", "mixed"} else []
    return _comparison_result(term, actual_ids, positions, include_details)


def compare_contract_to_actual(contract, *, include_details=False):
    memberships = ServiceMembership.objects.filter(status=ServiceMembership.Status.ACTIVE).values_list("service_id", "instance_id")
    active_by_service = defaultdict(set)
    for service_id, instance_id in memberships:
        active_by_service[service_id].add(instance_id)
    terms = list(
        contract.service_terms.select_related("service").prefetch_related(
            Prefetch("named_positions", queryset=NamedContractPosition.objects.all())
        )
    )
    results = []
    term_service_ids = set()
    for term in terms:
        term_service_ids.add(term.service_id)
        results.append(compare_contract_service_to_actual(term, include_details=include_details, actual_ids=active_by_service.get(term.service_id, set()), positions=list(term.named_positions.all())))
    for service in Service.objects.filter(is_active=True).exclude(pk__in=term_service_ids):
        actual_count = len(active_by_service.get(service.pk, set()))
        results.append({
            "term": None, "service": service, "mode": None, "contract_quantity": None, "actual_quantity": actual_count,
            "quantity_delta": None, "allowed_delta": None, "percent_delta": None, "status": "missing_term",
            "status_label": STATUS_LABELS["missing_term"], "composition_changed": False, "composition_delta": "—",
            "matched_count": 0, "added_count": actual_count, "missing_count": 0, "unresolved_count": 0, "incomplete": True,
        })
    results.sort(key=lambda item: item["service"].name)
    return {"contract": contract, "services": results, "captured_at": None, "summary": Counter(item["status"] for item in results)}


def comparison_for_term(term):
    """Backward-compatible detailed comparison used by legacy callers."""
    result = compare_contract_service_to_actual(term, include_details=True)
    return {
        **result,
        "matched": NamedContractPosition.objects.filter(pk__in=[position.pk for position in result["matched"]]),
        "contract_only": NamedContractPosition.objects.filter(pk__in=[position.pk for position in result["contract_only"]]),
        "unmatched": NamedContractPosition.objects.filter(pk__in=[position.pk for position in result["unmatched"]]),
        "ambiguous": NamedContractPosition.objects.filter(pk__in=[position.pk for position in result["ambiguous"]]),
    }


@transaction.atomic
def populate_contract_from_actual(contract, user=None):
    if contract.status != Contract.Status.DRAFT:
        raise ValidationError("Заполнение из актуального состояния доступно только для черновика.")
    if ContractActualSnapshot.objects.filter(contract=contract).exists():
        raise ValidationError("Черновик уже был заполнен из актуального состояния.")
    categories = list(ServiceMetricCategory.objects.select_for_update().select_related("service", "unit").filter(is_active=True, service__is_active=True).order_by("service__name", "name"))
    category_service_ids = {category.service_id for category in categories}
    from catalog.models import UnitOfMeasure
    pcs, _ = UnitOfMeasure.objects.get_or_create(code="pcs", defaults={"name": "Штука", "symbol": "шт."})
    for service in Service.objects.select_for_update().filter(is_active=True).exclude(pk__in=category_service_ids):
        categories.append(ServiceMetricCategory.objects.create(service=service, code=f"default-{service.pk}", name=service.name, unit=pcs, actual_value_method=ServiceMetricCategory.ActualValueMethod.MEMBER_COUNT))
    services = list({category.service for category in categories})
    memberships = list(
        ServiceMembership.objects.select_for_update().filter(service__in=services, status=ServiceMembership.Status.ACTIVE)
        .select_related("instance__instance_type").prefetch_related(
            Prefetch("instance__external_references", queryset=ExternalReference.objects.filter(source_system="glpi", external_object_type="Computer").select_related("glpi_computer"), to_attr="glpi_computer_references")
        )
    )
    members_by_service = defaultdict(list)
    for membership in memberships:
        members_by_service[membership.service_id].append(membership.instance)
    snapshot = ContractActualSnapshot.objects.create(contract=contract, captured_by=user)
    for category in categories:
        service = category.service
        instances = members_by_service[service.pk] if category.actual_value_method == "member_count" else []
        mode = service.default_accounting_mode
        actual_value, _, _ = actual_metric_for_category(category, [instance.pk for instance in instances])
        term = ContractServiceTerm.objects.create(
            contract=contract, service=service, metric_category=category, line_description=category.name, location=category.location, unit=category.unit, accounting_mode=mode,
            contracted_quantity=actual_value if mode in {"quantitative", "mixed"} else None,
            tolerance_type=ContractServiceTerm.ToleranceType.ABSOLUTE, tolerance_value=Decimal("0"),
            created_by=user, updated_by=user,
        )
        snapshot_service = ContractActualSnapshotService.objects.create(
            snapshot=snapshot, service=service, metric_category=category, contract_term=term, service_code=service.code or "",
            service_name=category.name, accounting_mode=mode, actual_quantity=actual_value or 0,
        )
        for instance in instances:
            reference = next(iter(getattr(instance, "glpi_computer_references", [])), None)
            glpi = getattr(reference, "glpi_computer", None) if reference else None
            ContractActualSnapshotInstance.objects.create(
                snapshot_service=snapshot_service, instance=instance, catalog_code=instance.catalog_code or "",
                name=instance.name, instance_type_name=instance.instance_type.name,
                glpi_inventory_number=glpi.inventory_number if glpi else "", glpi_serial_number=glpi.serial_number if glpi else "",
                glpi_location=glpi.location if glpi else "", glpi_external_id=reference.external_id if reference else "",
            )
            if mode in {"named", "mixed"}:
                NamedContractPosition.objects.create(
                    term=term, source_identifier=instance.catalog_code or "", source_name=instance.name,
                    source_data={"catalog_code": instance.catalog_code, "name": instance.name, "instance_type": instance.instance_type.name},
                    instance=instance, match_status=NamedContractPosition.MatchStatus.MATCHED, created_by=user, updated_by=user,
                )
    return snapshot


@transaction.atomic
def import_csv(term, csv_text, filename, user=None):
    if term.contract.status != Contract.Status.DRAFT:
        raise ValueError("Импорт перечня доступен только для черновика договора.")
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames or "catalog_code" not in reader.fieldnames:
        raise ValueError("CSV должен содержать заголовок catalog_code.")
    batch = ContractListImport.objects.create(term=term, original_filename=filename, file_hash=hashlib.sha256(csv_text.encode("utf-8")).hexdigest(), raw_csv=csv_text, created_by=user)
    stats = Counter()
    for row in reader:
        source_identifier = (row.get("catalog_code") or "").strip()
        matches = Instance.objects.filter(catalog_code=source_identifier)
        if not source_identifier:
            status, instance = NamedContractPosition.MatchStatus.UNMATCHED, None
        elif matches.count() == 1:
            status, instance = NamedContractPosition.MatchStatus.MATCHED, matches.first()
        elif matches.exists():
            status, instance = NamedContractPosition.MatchStatus.AMBIGUOUS, None
        else:
            status, instance = NamedContractPosition.MatchStatus.UNMATCHED, None
        NamedContractPosition.objects.create(term=term, source_identifier=source_identifier, source_name=(row.get("name") or "").strip(), source_data=row, instance=instance, match_status=status, import_batch=batch, created_by=user, updated_by=user)
        stats[status] += 1
    batch.total_rows = sum(stats.values()); batch.matched_rows = stats[NamedContractPosition.MatchStatus.MATCHED]; batch.unmatched_rows = stats[NamedContractPosition.MatchStatus.UNMATCHED]; batch.ambiguous_rows = stats[NamedContractPosition.MatchStatus.AMBIGUOUS]; batch.status = ContractListImport.Status.COMPLETED
    batch.save(update_fields=["total_rows", "matched_rows", "unmatched_rows", "ambiguous_rows", "status", "updated_at"])
    return batch
