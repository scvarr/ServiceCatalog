from django.contrib import admin
from .models import Contract, ContractActualSnapshot, ContractActualSnapshotInstance, ContractActualSnapshotService, ContractListImport, ContractServiceTerm, NamedContractPosition


class ContractServiceTermInline(admin.TabularInline):
    model = ContractServiceTerm
    extra = 0

    def has_change_permission(self, request, obj=None):
        return bool(obj and obj.status == Contract.Status.DRAFT and super().has_change_permission(request, obj))


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "period_label", "start_date", "end_date", "status")
    list_filter = ("status",)
    search_fields = ("number", "name")
    inlines = (ContractServiceTermInline,)


@admin.register(ContractServiceTerm)
class ContractServiceTermAdmin(admin.ModelAdmin):
    list_display = ("contract", "service", "accounting_mode", "contracted_quantity", "tolerance_value")
    list_filter = ("accounting_mode", "contract")
    search_fields = ("service__code", "service__name", "contract__number")

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields) if obj and obj.contract.status != Contract.Status.DRAFT else ()


@admin.register(NamedContractPosition)
class NamedContractPositionAdmin(admin.ModelAdmin):
    list_display = ("source_identifier", "source_name", "term", "instance", "match_status", "import_batch")
    list_filter = ("match_status", "term__contract")
    search_fields = ("source_identifier", "source_name", "instance__catalog_code")

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields) if obj and obj.term.contract.status != Contract.Status.DRAFT else ()


@admin.register(ContractListImport)
class ContractListImportAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "term", "status", "total_rows", "matched_rows", "unmatched_rows", "created_at")
    list_filter = ("status",)
    readonly_fields = ("file_hash", "raw_csv", "total_rows", "matched_rows", "unmatched_rows", "ambiguous_rows")


@admin.register(ContractActualSnapshot)
class ContractActualSnapshotAdmin(admin.ModelAdmin):
    list_display = ("contract", "captured_at", "captured_by")
    readonly_fields = tuple(field.name for field in ContractActualSnapshot._meta.fields)


@admin.register(ContractActualSnapshotService)
class ContractActualSnapshotServiceAdmin(admin.ModelAdmin):
    list_display = ("snapshot", "service_name", "accounting_mode", "actual_quantity")
    readonly_fields = tuple(field.name for field in ContractActualSnapshotService._meta.fields)


@admin.register(ContractActualSnapshotInstance)
class ContractActualSnapshotInstanceAdmin(admin.ModelAdmin):
    list_display = ("snapshot_service", "catalog_code", "name", "instance_type_name")
    readonly_fields = tuple(field.name for field in ContractActualSnapshotInstance._meta.fields)
