from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from .glpi import GlpiError
from .glpi_sync import sync_glpi_reference
from .models import ExternalReference, Instance, InstanceType, Service


@login_required
def service_list(request):
    services = Service.objects.annotate(member_count=Count("memberships")).order_by("name")
    return render(request, "catalog/service_list.html", {"services": services})


@login_required
def service_detail(request, pk):
    service = get_object_or_404(Service, pk=pk)
    memberships = service.memberships.select_related("instance").filter(status="active")
    return render(request, "catalog/service_detail.html", {"service": service, "memberships": memberships})


@login_required
def instance_list(request):
    instances = Instance.objects.select_related("instance_type").all()
    query = request.GET.get("q", "").strip()
    if query:
        instances = instances.filter(Q(name__icontains=query) | Q(catalog_code__icontains=query))
    if instance_type := request.GET.get("type"):
        instances = instances.filter(instance_type_id=instance_type)
    if status := request.GET.get("status"):
        instances = instances.filter(status=status)
    return render(request, "catalog/instance_list.html", {"instances": instances, "types": InstanceType.objects.filter(is_active=True)})


@login_required
def instance_detail(request, pk):
    instance = get_object_or_404(Instance.objects.select_related("instance_type"), pk=pk)
    memberships = instance.service_memberships.select_related("service").all()
    glpi_reference = instance.external_references.filter(source_system="glpi", external_object_type="Computer").select_related("glpi_computer").first()
    return render(request, "catalog/instance_detail.html", {"instance": instance, "memberships": memberships, "glpi_reference": glpi_reference})


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
