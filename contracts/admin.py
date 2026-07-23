from django.contrib import admin
from .models import Contract, ContractListImport, ContractServiceTerm, NamedContractPosition


class ContractServiceTermInline(admin.TabularInline):
    model = ContractServiceTerm
    extra = 0


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


@admin.register(NamedContractPosition)
class NamedContractPositionAdmin(admin.ModelAdmin):
    list_display = ("source_identifier", "source_name", "term", "instance", "match_status", "import_batch")
    list_filter = ("match_status", "term__contract")
    search_fields = ("source_identifier", "source_name", "instance__catalog_code")


@admin.register(ContractListImport)
class ContractListImportAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "term", "status", "total_rows", "matched_rows", "unmatched_rows", "created_at")
    list_filter = ("status",)
    readonly_fields = ("file_hash", "raw_csv", "total_rows", "matched_rows", "unmatched_rows", "ambiguous_rows")

