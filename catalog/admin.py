from django.contrib import admin
from .models import ActualServiceMetric, ExternalReference, GlpiComputerSnapshot, GlpiImportCandidate, GlpiImportPayload, GlpiImportSession, Instance, InstanceType, ListViewPreference, ServerProfile, Service, ServiceMembership, ServiceMetricCategory, UnitOfMeasure


@admin.register(InstanceType)
class InstanceTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


class ExternalReferenceInline(admin.TabularInline):
    model = ExternalReference
    extra = 0
    fields = ("source_system", "external_object_type", "external_id", "external_url", "last_sync_status", "last_synced_at", "last_sync_error")
    readonly_fields = ("last_sync_status", "last_synced_at", "last_sync_error")


@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
    list_display = ("catalog_code", "name", "instance_type", "status", "source", "updated_at")
    list_filter = ("instance_type", "status", "source")
    search_fields = ("catalog_code", "name")
    readonly_fields = ("catalog_code",)
    inlines = (ExternalReferenceInline,)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "default_accounting_mode", "is_active", "updated_at")
    list_filter = ("is_active", "default_accounting_mode")
    search_fields = ("code", "name")
    readonly_fields = ("code",)


@admin.register(ServiceMembership)
class ServiceMembershipAdmin(admin.ModelAdmin):
    list_display = ("service", "instance", "included_at", "excluded_at", "status")
    list_filter = ("status", "service")
    search_fields = ("service__code", "instance__catalog_code", "instance__name")


@admin.register(ExternalReference)
class ExternalReferenceAdmin(admin.ModelAdmin):
    list_display = ("instance", "source_system", "external_object_type", "external_id", "last_sync_status", "last_synced_at")
    list_filter = ("source_system", "external_object_type", "last_sync_status")
    search_fields = ("instance__catalog_code", "external_id")
    readonly_fields = ("last_synced_at", "last_sync_status", "last_sync_error")


@admin.register(GlpiComputerSnapshot)
class GlpiComputerSnapshotAdmin(admin.ModelAdmin):
    list_display = ("reference", "external_name", "inventory_number", "external_status", "last_inventory_update")
    readonly_fields = tuple(field.name for field in GlpiComputerSnapshot._meta.fields)


admin.site.register((UnitOfMeasure, ServiceMetricCategory, ActualServiceMetric, ServerProfile, GlpiImportSession, GlpiImportPayload, GlpiImportCandidate))


@admin.register(ListViewPreference)
class ListViewPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "page_key", "page_size")
    readonly_fields = ("user", "page_key", "visible_columns", "page_size")
