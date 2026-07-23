from django.db import migrations, models


def populate_missing_codes(apps, schema_editor):
    Instance = apps.get_model("catalog", "Instance")
    Service = apps.get_model("catalog", "Service")
    for instance in Instance.objects.filter(catalog_code__isnull=True):
        instance.catalog_code = f"INS-{instance.pk:06d}"
        instance.save(update_fields=["catalog_code"])
    for service in Service.objects.filter(code__isnull=True):
        service.code = f"SVC-{service.pk:06d}"
        service.save(update_fields=["code"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]
    operations = [
        migrations.RemoveIndex(model_name="instancetype", name="catalog_ins_is_acti_19ef70_idx"),
        migrations.RemoveIndex(model_name="service", name="catalog_ser_is_acti_0d1d5b_idx"),
        migrations.RemoveField(model_name="instancetype", name="code"),
        migrations.AlterField(
            model_name="instance",
            name="catalog_code",
            field=models.CharField(blank=True, editable=False, max_length=128, null=True, unique=True, verbose_name="системный код"),
        ),
        migrations.AlterField(
            model_name="service",
            name="code",
            field=models.CharField(blank=True, editable=False, max_length=64, null=True, unique=True, verbose_name="системный код"),
        ),
        migrations.RunPython(populate_missing_codes, migrations.RunPython.noop),
        migrations.AddIndex(model_name="instancetype", index=models.Index(fields=["is_active", "name"], name="catalog_type_active_name_idx")),
        migrations.AddIndex(model_name="service", index=models.Index(fields=["is_active", "name"], name="catalog_svc_active_name_idx")),
    ]
