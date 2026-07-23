from django.contrib import admin
from .models import Instance, InstanceType, Service, ServiceMembership


@admin.register(InstanceType)
class InstanceTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
    list_display = ("catalog_code", "name", "instance_type", "status", "source", "updated_at")
    list_filter = ("instance_type", "status", "source")
    search_fields = ("catalog_code", "name")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "default_accounting_mode", "is_active", "updated_at")
    list_filter = ("is_active", "default_accounting_mode")
    search_fields = ("code", "name")


@admin.register(ServiceMembership)
class ServiceMembershipAdmin(admin.ModelAdmin):
    list_display = ("service", "instance", "included_at", "excluded_at", "status")
    list_filter = ("status", "service")
    search_fields = ("service__code", "instance__catalog_code", "instance__name")

