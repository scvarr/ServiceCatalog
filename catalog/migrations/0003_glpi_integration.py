import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0002_generated_system_codes")]
    operations = [
        migrations.CreateModel(
            name="ExternalReference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_system", models.CharField(choices=[("glpi", "GLPI")], max_length=32, verbose_name="внешняя система")),
                ("external_object_type", models.CharField(max_length=64, verbose_name="тип внешнего объекта")), ("external_id", models.CharField(max_length=255, verbose_name="внешний ID")),
                ("external_url", models.URLField(blank=True, verbose_name="ссылка")), ("last_synced_at", models.DateTimeField(blank=True, null=True, verbose_name="последняя успешная синхронизация")),
                ("last_sync_status", models.CharField(choices=[("pending", "Не синхронизировано"), ("success", "Успешно"), ("error", "Ошибка")], default="pending", max_length=16, verbose_name="статус синхронизации")),
                ("last_sync_error", models.CharField(blank=True, max_length=500, verbose_name="последняя ошибка")),
                ("instance", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="external_references", to="catalog.instance", verbose_name="экземпляр")),
            ], options={"verbose_name": "внешняя ссылка", "verbose_name_plural": "внешние ссылки"},
        ),
        migrations.CreateModel(
            name="GlpiComputerSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("external_name", models.CharField(blank=True, max_length=255, verbose_name="имя в GLPI")), ("inventory_number", models.CharField(blank=True, max_length=255, verbose_name="инвентарный номер")),
                ("serial_number", models.CharField(blank=True, max_length=255, verbose_name="серийный номер")), ("external_uuid", models.CharField(blank=True, max_length=255, verbose_name="UUID")),
                ("external_status", models.CharField(blank=True, max_length=255, verbose_name="статус GLPI")), ("manufacturer", models.CharField(blank=True, max_length=255, verbose_name="производитель")),
                ("model", models.CharField(blank=True, max_length=255, verbose_name="модель")), ("external_type", models.CharField(blank=True, max_length=255, verbose_name="тип GLPI")),
                ("location", models.CharField(blank=True, max_length=255, verbose_name="местоположение")), ("entity_name", models.CharField(blank=True, max_length=255, verbose_name="сущность")),
                ("comment", models.TextField(blank=True, verbose_name="комментарий GLPI")), ("inventory_source", models.CharField(blank=True, max_length=255, verbose_name="источник инвентаризации")),
                ("external_created_at", models.DateTimeField(blank=True, null=True, verbose_name="создан в GLPI")), ("external_updated_at", models.DateTimeField(blank=True, null=True, verbose_name="изменен в GLPI")),
                ("last_inventory_update", models.DateTimeField(blank=True, null=True, verbose_name="последняя инвентаризация")), ("last_boot", models.DateTimeField(blank=True, null=True, verbose_name="последняя загрузка")),
                ("reference", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="glpi_computer", to="catalog.externalreference", verbose_name="внешняя ссылка")),
            ], options={"verbose_name": "данные компьютера GLPI", "verbose_name_plural": "данные компьютеров GLPI"},
        ),
        migrations.AddIndex(model_name="externalreference", index=models.Index(fields=["instance", "source_system"], name="cat_ext_inst_src_idx")),
        migrations.AddConstraint(model_name="externalreference", constraint=models.UniqueConstraint(fields=("source_system", "external_object_type", "external_id"), name="unique_external_object")),
    ]
