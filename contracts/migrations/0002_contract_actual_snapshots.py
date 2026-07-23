import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0006_listviewpreference_glpi_computer_data"), ("contracts", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="ContractActualSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("captured_at", models.DateTimeField(auto_now_add=True, verbose_name="зафиксирован")),
                ("captured_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="captured_contract_snapshots", to=settings.AUTH_USER_MODEL, verbose_name="зафиксировал")),
                ("contract", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="actual_snapshot", to="contracts.contract", verbose_name="договор")),
            ], options={"verbose_name": "снимок актуального состояния договора", "verbose_name_plural": "снимки актуального состояния договоров"},
        ),
        migrations.CreateModel(
            name="ContractActualSnapshotService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("service_code", models.CharField(blank=True, max_length=64, verbose_name="код услуги")), ("service_name", models.CharField(max_length=255, verbose_name="наименование услуги")),
                ("accounting_mode", models.CharField(choices=[("quantitative", "Количественный"), ("named", "Поименный"), ("mixed", "Смешанный"), ("none", "Без контроля")], max_length=16, verbose_name="способ учета")),
                ("actual_quantity", models.PositiveIntegerField(verbose_name="актуальное количество")),
                ("contract_term", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="actual_snapshot_service", to="contracts.contractserviceterm", verbose_name="условие договора")),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="actual_snapshot_services", to="catalog.service", verbose_name="услуга")),
                ("snapshot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="services", to="contracts.contractactualsnapshot", verbose_name="снимок")),
            ], options={"verbose_name": "услуга в снимке договора", "verbose_name_plural": "услуги в снимке договора"},
        ),
        migrations.CreateModel(
            name="ContractActualSnapshotInstance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("catalog_code", models.CharField(max_length=128, verbose_name="системный код")), ("name", models.CharField(max_length=255, verbose_name="наименование")),
                ("instance_type_name", models.CharField(blank=True, max_length=255, verbose_name="тип")), ("glpi_inventory_number", models.CharField(blank=True, max_length=255, verbose_name="инвентарный номер GLPI")),
                ("glpi_serial_number", models.CharField(blank=True, max_length=255, verbose_name="серийный номер GLPI")), ("glpi_location", models.CharField(blank=True, max_length=255, verbose_name="местоположение GLPI")), ("glpi_external_id", models.CharField(blank=True, max_length=255, verbose_name="внешний ID GLPI")),
                ("instance", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="actual_snapshot_instances", to="catalog.instance", verbose_name="экземпляр")),
                ("snapshot_service", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="instances", to="contracts.contractactualsnapshotservice", verbose_name="услуга снимка")),
            ], options={"verbose_name": "экземпляр в снимке договора", "verbose_name_plural": "экземпляры в снимке договора"},
        ),
        migrations.AddConstraint(model_name="contractactualsnapshotservice", constraint=models.UniqueConstraint(fields=("snapshot", "service"), name="contracts_snapshot_service_unique")),
        migrations.AddConstraint(model_name="contractactualsnapshotinstance", constraint=models.UniqueConstraint(fields=("snapshot_service", "catalog_code"), name="contracts_snapshot_instance_unique")),
    ]
