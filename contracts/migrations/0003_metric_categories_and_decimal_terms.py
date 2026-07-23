from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


def populate_legacy_categories(apps, schema_editor):
    Unit = apps.get_model("catalog", "UnitOfMeasure")
    Category = apps.get_model("catalog", "ServiceMetricCategory")
    Term = apps.get_model("contracts", "ContractServiceTerm")
    pcs, _ = Unit.objects.get_or_create(code="pcs", defaults={"name": "Штука", "symbol": "шт."})
    for term in Term.objects.select_related("service"):
        category, _ = Category.objects.get_or_create(service=term.service, code=f"legacy-{term.service_id}", defaults={"name": term.service.name, "unit": pcs, "actual_value_method": "member_count"})
        term.metric_category_id = category.pk
        term.unit_id = pcs.pk
        term.line_description = term.service.name
        term.save(update_fields=["metric_category", "unit", "line_description"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0007_operational_metrics_profiles_glpi_import"), ("contracts", "0002_contract_actual_snapshots")]
    operations = [
        migrations.RemoveConstraint(model_name="contractserviceterm", name="unique_contract_service_term"),
        migrations.AddField(model_name="contractserviceterm", name="line_description", field=models.CharField(blank=True, max_length=255, verbose_name="описание позиции")),
        migrations.AddField(model_name="contractserviceterm", name="location", field=models.CharField(blank=True, max_length=255, verbose_name="место оказания")),
        migrations.AddField(model_name="contractserviceterm", name="metric_category", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="contract_terms", to="catalog.servicemetriccategory", verbose_name="категория учета")),
        migrations.AddField(model_name="contractserviceterm", name="unit", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="contract_terms", to="catalog.unitofmeasure", verbose_name="единица")),
        migrations.AlterField(model_name="contractserviceterm", name="contracted_quantity", field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True, verbose_name="договорное количество")),
        migrations.RunPython(populate_legacy_categories, migrations.RunPython.noop),
        migrations.AddConstraint(model_name="contractserviceterm", constraint=models.UniqueConstraint(condition=models.Q(("metric_category__isnull", False)), fields=("contract", "metric_category"), name="unique_contract_metric_category")),
    ]
