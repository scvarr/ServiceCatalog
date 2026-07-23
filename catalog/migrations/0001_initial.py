import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="InstanceType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=64, unique=True, verbose_name="код")),
                ("name", models.CharField(max_length=255, verbose_name="наименование")),
                ("is_active", models.BooleanField(default=True, verbose_name="активен")),
            ], options={"verbose_name": "тип экземпляра", "verbose_name_plural": "типы экземпляров", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Service",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=64, unique=True, verbose_name="код")),
                ("name", models.CharField(max_length=255, verbose_name="наименование")),
                ("description", models.TextField(blank=True, verbose_name="описание")),
                ("is_active", models.BooleanField(default=True, verbose_name="активна")),
                ("default_accounting_mode", models.CharField(choices=[("quantitative", "Количественный"), ("named", "Поименный"), ("mixed", "Смешанный"), ("none", "Без контроля")], default="none", max_length=16, verbose_name="способ учета по умолчанию")),
            ], options={"verbose_name": "услуга", "verbose_name_plural": "услуги", "ordering": ["code"]},
        ),
        migrations.CreateModel(
            name="Instance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("catalog_code", models.CharField(max_length=128, unique=True, verbose_name="каталожный код")),
                ("name", models.CharField(max_length=255, verbose_name="наименование")),
                ("status", models.CharField(choices=[("active", "Активен"), ("inactive", "Неактивен"), ("retired", "Выведен из эксплуатации")], default="active", max_length=16, verbose_name="состояние")),
                ("source", models.CharField(choices=[("manual", "Вручную")], default="manual", max_length=32, verbose_name="источник")),
                ("notes", models.TextField(blank=True, verbose_name="примечание")),
                ("instance_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="instances", to="catalog.instancetype", verbose_name="тип")),
            ], options={"verbose_name": "экземпляр", "verbose_name_plural": "экземпляры", "ordering": ["catalog_code"]},
        ),
        migrations.CreateModel(
            name="ServiceMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("included_at", models.DateField(default=django.utils.timezone.localdate, verbose_name="дата включения")), ("excluded_at", models.DateField(blank=True, null=True, verbose_name="дата исключения")),
                ("status", models.CharField(choices=[("active", "Активно"), ("excluded", "Исключено")], default="active", max_length=16, verbose_name="состояние")),
                ("reason", models.TextField(blank=True, verbose_name="основание / примечание")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_memberships", to=settings.AUTH_USER_MODEL, verbose_name="создал")),
                ("instance", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="service_memberships", to="catalog.instance", verbose_name="экземпляр")),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="catalog.service", verbose_name="услуга")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="updated_memberships", to=settings.AUTH_USER_MODEL, verbose_name="изменил")),
            ], options={"verbose_name": "участие экземпляра в услуге", "verbose_name_plural": "состав услуг", "ordering": ["service", "-included_at"]},
        ),
        migrations.AddIndex(model_name="instancetype", index=models.Index(fields=["is_active", "code"], name="catalog_ins_is_acti_19ef70_idx")),
        migrations.AddIndex(model_name="service", index=models.Index(fields=["is_active", "code"], name="catalog_ser_is_acti_0d1d5b_idx")),
        migrations.AddIndex(model_name="instance", index=models.Index(fields=["instance_type", "status"], name="catalog_ins_instanc_183ec5_idx")),
        migrations.AddIndex(model_name="servicemembership", index=models.Index(fields=["service", "status", "included_at"], name="catalog_ser_service_fe6e77_idx")),
        migrations.AddIndex(model_name="servicemembership", index=models.Index(fields=["instance", "status"], name="catalog_ser_instanc_76029e_idx")),
        migrations.AddConstraint(model_name="servicemembership", constraint=models.UniqueConstraint(condition=Q(("status", "active")), fields=("service", "instance"), name="unique_active_service_membership")),
        migrations.AddConstraint(model_name="servicemembership", constraint=models.CheckConstraint(condition=Q(("excluded_at__isnull", True), ("excluded_at__gte", models.F("included_at")), _connector="OR"), name="membership_dates_ordered")),
    ]
