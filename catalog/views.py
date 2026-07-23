from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from .models import Instance, InstanceType, Service


@login_required
def service_list(request):
    services = Service.objects.annotate(member_count=Count("memberships")).order_by("code")
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
    return render(request, "catalog/instance_detail.html", {"instance": instance, "memberships": memberships})
