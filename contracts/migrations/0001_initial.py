import decimal
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL), ("catalog", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="Contract",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("number", models.CharField(max_length=128, unique=True, verbose_name="номер")), ("name", models.CharField(max_length=255, verbose_name="наименование")),
                ("period_label", models.CharField(blank=True, max_length=64, verbose_name="период")), ("start_date", models.DateField(verbose_name="дата начала")), ("end_date", models.DateField(verbose_name="дата окончания")),
                ("status", models.CharField(choices=[("draft", "Черновик"), ("active", "Действующий"), ("archived", "Архивный")], default="draft", max_length=16, verbose_name="статус")),
                ("notes", models.TextField(blank=True, verbose_name="примечание")), ("document_url", models.URLField(blank=True, verbose_name="ссылка на документ")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_contracts", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="updated_contracts", to=settings.AUTH_USER_MODEL)),
            ], options={"verbose_name": "договор", "verbose_name_plural": "договоры", "ordering": ["-start_date"]},
        ),
        migrations.CreateModel(
            name="ContractServiceTerm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("accounting_mode", models.CharField(choices=[("quantitative", "Количественный"), ("named", "Поименный"), ("mixed", "Смешанный"), ("none", "Без контроля")], max_length=16, verbose_name="способ учета")),
                ("contracted_quantity", models.PositiveIntegerField(blank=True, null=True, verbose_name="договорное количество")),
                ("tolerance_type", models.CharField(choices=[("percent", "Процент"), ("absolute", "Абсолютное")], default="absolute", max_length=16, verbose_name="тип допуска")),
                ("tolerance_value", models.DecimalField(decimal_places=2, default=decimal.Decimal("0"), max_digits=10, verbose_name="допуск")),
                ("quantitative_reserve", models.PositiveIntegerField(blank=True, null=True, verbose_name="количественный резерв")), ("notes", models.TextField(blank=True, verbose_name="примечание")),
                ("contract", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_terms", to="contracts.contract", verbose_name="договор")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_contract_terms", to=settings.AUTH_USER_MODEL)),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contract_terms", to="catalog.service", verbose_name="услуга")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="updated_contract_terms", to=settings.AUTH_USER_MODEL)),
            ], options={"verbose_name": "условие услуги договора", "verbose_name_plural": "условия услуг договора"},
        ),
        migrations.CreateModel(
            name="ContractListImport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("original_filename", models.CharField(max_length=255, verbose_name="имя файла")), ("file_hash", models.CharField(max_length=64, verbose_name="SHA-256")), ("raw_csv", models.TextField(verbose_name="исходный CSV")),
                ("status", models.CharField(choices=[("pending", "Ожидает"), ("completed", "Завершен"), ("failed", "Ошибка")], default="pending", max_length=16, verbose_name="статус")),
                ("total_rows", models.PositiveIntegerField(default=0, verbose_name="строк")), ("matched_rows", models.PositiveIntegerField(default=0, verbose_name="сопоставлено")), ("unmatched_rows", models.PositiveIntegerField(default=0, verbose_name="не сопоставлено")), ("ambiguous_rows", models.PositiveIntegerField(default=0, verbose_name="неоднозначно")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="contract_imports", to=settings.AUTH_USER_MODEL)),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="imports", to="contracts.contractserviceterm", verbose_name="условие")),
            ], options={"verbose_name": "импорт договорного перечня", "verbose_name_plural": "импорты договорных перечней", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="NamedContractPosition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_identifier", models.CharField(max_length=255, verbose_name="исходный идентификатор")), ("source_name", models.CharField(blank=True, max_length=255, verbose_name="исходное наименование")), ("source_data", models.JSONField(blank=True, default=dict, verbose_name="исходные данные")),
                ("match_status", models.CharField(choices=[("matched", "Сопоставлено"), ("unmatched", "Не сопоставлено"), ("ambiguous", "Неоднозначно"), ("ignored", "Игнорируется")], default="unmatched", max_length=16, verbose_name="состояние сопоставления")), ("comment", models.TextField(blank=True, verbose_name="комментарий")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_contract_positions", to=settings.AUTH_USER_MODEL)),
                ("import_batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="positions", to="contracts.contractlistimport", verbose_name="пакет импорта")),
                ("instance", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="contract_positions", to="catalog.instance", verbose_name="экземпляр")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="named_positions", to="contracts.contractserviceterm", verbose_name="условие")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="updated_contract_positions", to=settings.AUTH_USER_MODEL)),
            ], options={"verbose_name": "поименная договорная позиция", "verbose_name_plural": "поименные договорные позиции"},
        ),
        migrations.AddIndex(model_name="contractserviceterm", index=models.Index(fields=["contract", "accounting_mode"], name="contracts_c_contrac_88aa2b_idx")),
        migrations.AddIndex(model_name="namedcontractposition", index=models.Index(fields=["term", "match_status"], name="contracts_n_term_id_532abf_idx")),
        migrations.AddIndex(model_name="namedcontractposition", index=models.Index(fields=["source_identifier"], name="contracts_n_source__f202dc_idx")),
        migrations.AddConstraint(model_name="contract", constraint=models.UniqueConstraint(condition=Q(("status", "active")), fields=("status",), name="one_active_contract")),
        migrations.AddConstraint(model_name="contract", constraint=models.UniqueConstraint(condition=Q(("status", "draft")), fields=("status",), name="one_draft_contract")),
        migrations.AddConstraint(model_name="contract", constraint=models.CheckConstraint(condition=Q(("end_date__gte", models.F("start_date"))), name="contract_dates_ordered")),
        migrations.AddConstraint(model_name="contractserviceterm", constraint=models.UniqueConstraint(fields=("contract", "service"), name="unique_contract_service_term")),
        migrations.AddConstraint(model_name="namedcontractposition", constraint=models.UniqueConstraint(condition=Q(("instance__isnull", False), ("match_status", "matched")), fields=("term", "instance"), name="unique_matched_instance_per_term")),
    ]
