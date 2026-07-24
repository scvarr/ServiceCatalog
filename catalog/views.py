from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .glpi import GlpiError
from .glpi_sync import sync_glpi_reference
from .glpi_import import apply_glpi_candidates, create_glpi_import
from .glpi_diagnostics import build_glpi_diagnostic_archive
from .glpi_database import diagnostic_summary
from .glpi_cache import create_instances_from_glpi_cache, refresh_glpi_lookups, sync_glpi_cache
from .forms import GlpiCachedComputerImportForm, GlpiCacheFilterForm, GlpiCacheSyncFilterForm
from .listing import (
    DEFAULT_PAGE_SIZE,
    GLPI_COMPUTER_COLUMNS,
    INSTANCE_COLUMNS,
    PAGE_SIZES,
    SERVICE_MEMBERSHIP_COLUMNS,
    SERVICE_COLUMNS,
    column_specs,
    normalize_columns,
    normalize_page_size,
    paginate,
    query_string,
    visible_columns,
)
from .models import ActualServiceMetric, ExternalReference, GlpiCacheSyncRun, GlpiCachedComputer, GlpiImportSession, Instance, InstanceType, ListViewPreference, Service, ServiceMembership, ServiceMetricCategory


LIST_PARAMETERS = {
    ListViewPreference.PageKey.SERVICE_LIST: ("q", "page", "page_size"),
    ListViewPreference.PageKey.INSTANCE_LIST: ("q", "type", "status", "page", "page_size"),
    ListViewPreference.PageKey.SERVICE_MEMBERSHIP_LIST: ("q", "page", "page_size"),
    ListViewPreference.PageKey.GLPI_COMPUTER_DATA: (),
}


def _preference(request, page_key):
    return ListViewPreference.objects.filter(user=request.user, page_key=page_key).first()


def _list_state(request, page_key, columns):
    preference = _preference(request, page_key)
    stored_columns = preference.visible_columns if preference else None
    keys = visible_columns(stored_columns, columns)
    fallback_size = normalize_page_size(preference.page_size if preference else None)
    page_size = normalize_page_size(request.GET.get("page_size"), fallback_size)
    return keys, page_size


def _redirect_after_preference_update(request, page_key):
    params = query_string(request.POST, LIST_PARAMETERS[page_key])
    return redirect(f"{request.path}?{params}" if params else request.path)


def _save_preference(request, page_key, columns):
    if request.method != "POST":
        return None

    if request.POST.get("action") == "reset_preferences":
        ListViewPreference.objects.filter(user=request.user, page_key=page_key).delete()
        messages.success(request, "Настройки списка возвращены к значениям по умолчанию.")
        return _redirect_after_preference_update(request, page_key)

    action = request.POST.get("action")
    if action == "save_page_size":
        preference = _preference(request, page_key)
        selected = visible_columns(preference.visible_columns if preference else None, columns)
    else:
        selected = normalize_columns(request.POST.getlist("visible_columns"), columns)
    page_size = normalize_page_size(request.POST.get("page_size"), DEFAULT_PAGE_SIZE)
    ListViewPreference.objects.update_or_create(
        user=request.user,
        page_key=page_key,
        defaults={"visible_columns": selected, "page_size": page_size},
    )
    messages.success(request, "Настройки списка сохранены.")
    return _redirect_after_preference_update(request, page_key)


def _list_context(request, queryset, page_key, columns, keys, page_size, **extra):
    page_obj, page_range = paginate(queryset, request.GET.get("page"), page_size)
    current_query = query_string(request.GET, LIST_PARAMETERS[page_key], exclude=("page",))
    return {
        "page_obj": page_obj,
        "page_range": page_range,
        "page_query": current_query,
        "query": request.GET.get("q", "").strip(),
        "page_sizes": PAGE_SIZES,
        "page_size": page_size,
        "columns": columns,
        "visible_column_keys": keys,
        "visible_columns": column_specs(keys, columns),
        "page_key": page_key,
        **extra,
    }


@login_required
def service_list(request):
    page_key = ListViewPreference.PageKey.SERVICE_LIST
    post_response = _save_preference(request, page_key, SERVICE_COLUMNS)
    if post_response:
        return post_response

    keys, page_size = _list_state(request, page_key, SERVICE_COLUMNS)
    query = request.GET.get("q", "").strip()
    services = Service.objects.all()
    if query:
        related_instance_matches = ServiceMembership.objects.filter(service_id=OuterRef("pk")).filter(
            Q(instance__name__icontains=query)
            | Q(instance__catalog_code__icontains=query)
            | Q(instance__instance_type__name__icontains=query)
        )
        services = services.filter(
            Q(name__icontains=query)
            | Q(code__icontains=query)
            | Q(description__icontains=query)
            | Exists(related_instance_matches)
        )
    services = services.annotate(
        member_count=Count(
            "memberships",
            filter=Q(memberships__status=ServiceMembership.Status.ACTIVE),
            distinct=True,
        )
    ).order_by("name")
    context = _list_context(request, services, page_key, SERVICE_COLUMNS, keys, page_size, list_kind="service")
    contract_keys = {"contract_quantity", "actual_quantity", "contract_delta", "contract_status", "composition_delta"}
    if contract_keys & set(keys):
        from contracts.models import Contract
        from contracts.services import compare_contract_to_actual

        active_contract = Contract.objects.filter(status=Contract.Status.ACTIVE).first()
        comparisons = {}
        if active_contract:
            comparisons = {item["service"].pk: item for item in compare_contract_to_actual(active_contract)["services"]}
        for service in context["page_obj"]:
            service.contract_comparison = comparisons.get(service.pk)
    return render(request, "catalog/service_list.html", context)


@login_required
def service_detail(request, pk):
    service = get_object_or_404(Service, pk=pk)
    page_key = ListViewPreference.PageKey.SERVICE_MEMBERSHIP_LIST
    post_response = _save_preference(request, page_key, SERVICE_MEMBERSHIP_COLUMNS)
    if post_response:
        return post_response

    keys, page_size = _list_state(request, page_key, SERVICE_MEMBERSHIP_COLUMNS)
    query = request.GET.get("q", "").strip()
    memberships = service.memberships.select_related("instance__instance_type", "instance__server_profile").filter(status=ServiceMembership.Status.ACTIVE)
    if query:
        memberships = memberships.filter(
            Q(instance__name__icontains=query)
            | Q(instance__catalog_code__icontains=query)
            | Q(instance__instance_type__name__icontains=query)
            | Q(instance__notes__icontains=query)
            | Q(reason__icontains=query)
        )
    context = _list_context(
        request,
        memberships.order_by("-included_at", "instance__name"),
        page_key,
        SERVICE_MEMBERSHIP_COLUMNS,
        keys,
        page_size,
        list_kind="service_membership",
        service=service,
    )
    from contracts.models import Contract, ContractServiceTerm
    from contracts.services import compare_contract_service_to_actual

    active_contract = Contract.objects.filter(status=Contract.Status.ACTIVE).first()
    contract_comparison = None
    if active_contract:
        term = ContractServiceTerm.objects.filter(contract=active_contract, service=service).select_related("contract", "service").first()
        if term:
            contract_comparison = compare_contract_service_to_actual(term)
    context.update({"active_contract": active_contract, "contract_comparison": contract_comparison})
    return render(request, "catalog/service_detail.html", context)


@login_required
def instance_list(request):
    page_key = ListViewPreference.PageKey.INSTANCE_LIST
    post_response = _save_preference(request, page_key, INSTANCE_COLUMNS)
    if post_response:
        return post_response

    keys, page_size = _list_state(request, page_key, INSTANCE_COLUMNS)
    query = request.GET.get("q", "").strip()
    selected_type = request.GET.get("type", "")
    selected_status = request.GET.get("status", "")
    profile_keys = {"profile_model", "cpu_summary", "memory_total", "raid_controller", "hypervisor", "commissioned", "risk_level", "replacement_year"}
    instances = Instance.objects.select_related("instance_type", *(["server_profile"] if profile_keys & set(keys) else []))
    if query:
        related_service_matches = ServiceMembership.objects.filter(
            instance_id=OuterRef("pk"), status=ServiceMembership.Status.ACTIVE
        ).filter(Q(service__name__icontains=query) | Q(service__code__icontains=query))
        instances = instances.filter(
            Q(name__icontains=query)
            | Q(catalog_code__icontains=query)
            | Q(notes__icontains=query)
            | Q(instance_type__name__icontains=query)
            | Exists(related_service_matches)
        )
    if selected_type:
        instances = instances.filter(instance_type_id=selected_type)
    valid_statuses = {value for value, _ in Instance.Status.choices}
    if selected_status in valid_statuses:
        instances = instances.filter(status=selected_status)
    if "services" in keys:
        instances = instances.prefetch_related(
            Prefetch(
                "service_memberships",
                queryset=ServiceMembership.objects.filter(status=ServiceMembership.Status.ACTIVE).select_related("service"),
                to_attr="active_memberships",
            )
        )
    context = _list_context(
        request,
        instances,
        page_key,
        INSTANCE_COLUMNS,
        keys,
        page_size,
        list_kind="instance",
        types=InstanceType.objects.filter(is_active=True),
        selected_type=selected_type,
        selected_status=selected_status,
        status_choices=Instance.Status.choices,
    )
    return render(request, "catalog/instance_list.html", context)


@login_required
def instance_detail(request, pk):
    instance = get_object_or_404(Instance.objects.select_related("instance_type", "server_profile"), pk=pk)
    page_key = ListViewPreference.PageKey.GLPI_COMPUTER_DATA
    post_response = _save_preference(request, page_key, GLPI_COMPUTER_COLUMNS)
    if post_response:
        return post_response

    memberships = instance.service_memberships.select_related("service").all()
    glpi_reference = instance.external_references.filter(source_system="glpi", external_object_type="Computer").select_related("glpi_computer").first()
    glpi_keys, _ = _list_state(request, page_key, GLPI_COMPUTER_COLUMNS)
    latest_import = instance.glpi_import_sessions.order_by("-created_at").prefetch_related("candidates", "payloads").first()
    glpi_db_diagnostics = diagnostic_summary()
    glpi_db_diagnostics["last_result"] = "not_attempted"
    if latest_import:
        processor_db_payload = next(
            (payload for payload in latest_import.payloads.all() if payload.endpoint_key == "processor_db"), None
        )
        if processor_db_payload:
            if processor_db_payload.error:
                glpi_db_diagnostics["last_result"] = "error"
                glpi_db_diagnostics["last_error"] = processor_db_payload.error
            elif processor_db_payload.payload:
                glpi_db_diagnostics["last_result"] = "rows"
                glpi_db_diagnostics["row_count"] = len(processor_db_payload.payload)
            else:
                glpi_db_diagnostics["last_result"] = "empty"
    return render(
        request,
        "catalog/instance_detail.html",
        {
            "instance": instance,
            "memberships": memberships,
            "glpi_reference": glpi_reference,
            "glpi_columns": GLPI_COMPUTER_COLUMNS,
            "visible_glpi_columns": column_specs(glpi_keys, GLPI_COMPUTER_COLUMNS),
            "visible_glpi_column_keys": glpi_keys,
            "glpi_page_key": page_key,
            "latest_glpi_import": latest_import,
            "glpi_db_diagnostics": glpi_db_diagnostics,
        },
    )


@permission_required("catalog.change_instance", raise_exception=True)
def import_glpi_instance(request, pk):
    instance = get_object_or_404(Instance, pk=pk)
    if request.method == "POST":
        reference = instance.external_references.filter(source_system="glpi", external_object_type="Computer").first()
        if not reference:
            messages.error(request, "Для экземпляра не задана внешняя ссылка GLPI Computer.")
        else:
            session = create_glpi_import(reference, request.user)
            if session.status == GlpiImportSession.Status.COMPLETED:
                messages.success(request, "Импорт GLPI подготовлен.")
            elif session.status == GlpiImportSession.Status.PARTIAL:
                messages.warning(request, "Импорт GLPI подготовлен частично: доступные данные сохранены.")
            else:
                messages.error(request, "Импорт GLPI завершился с ошибкой.")
    return redirect("catalog:instance_detail", pk=pk)


@permission_required("catalog.delete_instance", raise_exception=True)
def export_glpi_diagnostics(request, pk):
    if request.method != "POST":
        return redirect("catalog:instance_detail", pk=pk)
    instance = get_object_or_404(Instance, pk=pk)
    reference = instance.external_references.filter(source_system="glpi", external_object_type="Computer").first()
    if not reference:
        messages.error(request, "Для экземпляра не задана внешняя ссылка GLPI Computer.")
        return redirect("catalog:instance_detail", pk=pk)
    try:
        response = HttpResponse(build_glpi_diagnostic_archive(reference), content_type="application/zip")
    except GlpiError as exc:
        messages.error(request, f"Не удалось подготовить диагностический пакет GLPI: {exc}")
        return redirect("catalog:instance_detail", pk=pk)
    response["Content-Disposition"] = f'attachment; filename="glpi-diagnostics-{instance.catalog_code}.zip"'
    return response


@permission_required("catalog.change_instance", raise_exception=True)
def apply_glpi_import(request, pk, session_pk):
    session = get_object_or_404(GlpiImportSession, pk=session_pk, instance_id=pk)
    if request.method == "POST":
        apply_glpi_candidates(session, request.POST.getlist("candidate_ids"), request.user)
        messages.success(request, "Выбранные предложения GLPI применены.")
    return redirect("catalog:instance_detail", pk=pk)


@permission_required("catalog.change_instance", raise_exception=True)
def sync_glpi_instance(request, pk):
    if request.method != "POST":
        return redirect("catalog:instance_detail", pk=pk)
    instance = get_object_or_404(Instance, pk=pk)
    reference = instance.external_references.filter(source_system="glpi", external_object_type="Computer").first()
    if not reference:
        messages.error(request, "Для экземпляра не задана внешняя ссылка GLPI Computer.")
    else:
        try:
            sync_glpi_reference(reference)
            messages.success(request, "Данные из GLPI успешно обновлены.")
        except GlpiError as exc:
            messages.error(request, f"Не удалось обновить данные GLPI: {exc}")
    return redirect("catalog:instance_detail", pk=pk)


@permission_required("catalog.view_glpicachedcomputer", raise_exception=True)
def glpi_cache_list(request):
    filters = GlpiCacheFilterForm(request.GET or None)
    computers = GlpiCachedComputer.objects.select_related("computer_type", "state", "location")
    if filters.is_valid():
        if not filters.cleaned_data.get("show_missing"):
            computers = computers.filter(is_missing=False)
        if filters.cleaned_data.get("computer_type"):
            computers = computers.filter(computer_type__external_id=filters.cleaned_data["computer_type"])
        if filters.cleaned_data.get("state"):
            computers = computers.filter(state__external_id=filters.cleaned_data["state"])
        if filters.cleaned_data.get("q"):
            query = filters.cleaned_data["q"]
            computers = computers.filter(Q(name__icontains=query) | Q(external_id__icontains=query) | Q(inventory_number__icontains=query))
    references = ExternalReference.objects.filter(source_system=ExternalReference.SourceSystem.GLPI, external_object_type="Computer", external_id=OuterRef("external_id"))
    computers = computers.annotate(is_linked=Exists(references))
    page_obj, page_range = paginate(computers, request.GET.get("page"), normalize_page_size(request.GET.get("page_size"), DEFAULT_PAGE_SIZE))
    selected = request.GET.getlist("selected")
    latest_run = GlpiCacheSyncRun.objects.first()
    return render(request, "catalog/glpi_cache_list.html", {"filter_form": filters, "sync_filter_form": GlpiCacheSyncFilterForm(), "page_obj": page_obj, "page_range": page_range, "latest_run": latest_run, "selected": selected, "import_form": GlpiCachedComputerImportForm(choices=[row.pk for row in page_obj if not row.is_linked]), "page_query": query_string(request.GET, ("computer_type", "state", "q", "show_missing", "page_size"), exclude=("page",))})


@permission_required("catalog.change_glpicachedcomputer", raise_exception=True)
def sync_glpi_cache_view(request):
    if request.method == "POST":
        filters = GlpiCacheSyncFilterForm(request.POST)
        rsql_filter = filters.rsql_filter() if filters.is_valid() else ""
        run = sync_glpi_cache(requested_by=request.user, rsql_filter=rsql_filter)
        if run.status == GlpiCacheSyncRun.Status.COMPLETED:
            messages.success(request, "Кэш GLPI обновлён.")
        elif run.status == GlpiCacheSyncRun.Status.PARTIAL:
            messages.warning(request, "Кэш GLPI обновлён частично.")
        else:
            messages.error(request, "Не удалось обновить кэш GLPI.")
    return redirect("catalog:glpi_cache_list")


@permission_required("catalog.change_glpicachedcomputer", raise_exception=True)
def refresh_glpi_cache_lookups_view(request):
    if request.method == "POST":
        run = refresh_glpi_lookups(requested_by=request.user)
        if run.status == GlpiCacheSyncRun.Status.COMPLETED:
            messages.success(request, "Справочники GLPI обновлены.")
        else:
            messages.warning(request, "Справочники GLPI обновлены частично.")
    return redirect("catalog:glpi_cache_list")


@permission_required("catalog.add_instance", raise_exception=True)
def import_glpi_cached_computers(request):
    if request.method != "POST":
        return redirect("catalog:glpi_cache_list")
    selected = request.POST.getlist("cached_computer_ids")
    form = GlpiCachedComputerImportForm(request.POST, choices=selected)
    if not form.is_valid():
        messages.error(request, "Не удалось проверить выбранные компьютеры.")
        return redirect("catalog:glpi_cache_list")
    service = form.cleaned_data["service"]
    if service and not request.user.has_perm("catalog.add_servicemembership"):
        messages.error(request, "Недостаточно прав для добавления экземпляров в услугу.")
        return redirect("catalog:glpi_cache_list")
    report = create_instances_from_glpi_cache([int(value) for value in form.cleaned_data["cached_computer_ids"]], instance_type=form.cleaned_data["instance_type"], service=service, user=request.user)
    messages.success(request, f"Создано экземпляров: {report['created']}; уже связанных: {report['already_linked']}.")
    return redirect("catalog:glpi_cache_list")
