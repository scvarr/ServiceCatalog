import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0007_operational_metrics_profiles_glpi_import"), ("contracts", "0003_metric_categories_and_decimal_terms")]
    operations = [
        migrations.RemoveConstraint(model_name="contractactualsnapshotservice", name="contracts_snapshot_service_unique"),
        migrations.AddField(model_name="contractactualsnapshotservice", name="metric_category", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="snapshot_services", to="catalog.servicemetriccategory", verbose_name="категория учета")),
        migrations.AlterField(model_name="contractactualsnapshotservice", name="actual_quantity", field=models.DecimalField(decimal_places=3, max_digits=14, verbose_name="актуальное количество")),
        migrations.AddConstraint(model_name="contractactualsnapshotservice", constraint=models.UniqueConstraint(condition=models.Q(("metric_category__isnull", False)), fields=("snapshot", "metric_category"), name="contracts_snapshot_category_unique")),
    ]
