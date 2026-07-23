from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render

from .glpi import GlpiError
from .glpi_sync import sync_glpi_reference
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
from .models import ExternalReference, Instance, InstanceType, ListViewPreference, Service, ServiceMembership


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
    memberships = service.memberships.select_related("instance__instance_type").filter(status=ServiceMembership.Status.ACTIVE)
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
    instances = Instance.objects.select_related("instance_type")
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
    instance = get_object_or_404(Instance.objects.select_related("instance_type"), pk=pk)
    page_key = ListViewPreference.PageKey.GLPI_COMPUTER_DATA
    post_response = _save_preference(request, page_key, GLPI_COMPUTER_COLUMNS)
    if post_response:
        return post_response

    memberships = instance.service_memberships.select_related("service").all()
    glpi_reference = instance.external_references.filter(source_system="glpi", external_object_type="Computer").select_related("glpi_computer").first()
    glpi_keys, _ = _list_state(request, page_key, GLPI_COMPUTER_COLUMNS)
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
        },
    )


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
