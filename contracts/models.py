from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from catalog.models import Instance, Service, ServiceMetricCategory, TimeStampedModel, UnitOfMeasure


class Contract(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        ACTIVE = "active", "Действующий"
        ARCHIVED = "archived", "Архивный"

    number = models.CharField("номер", max_length=128, unique=True)
    name = models.CharField("наименование", max_length=255)
    period_label = models.CharField("период", max_length=64, blank=True)
    start_date = models.DateField("дата начала")
    end_date = models.DateField("дата окончания")
    status = models.CharField("статус", max_length=16, choices=Status, default=Status.DRAFT)
    notes = models.TextField("примечание", blank=True)
    document_url = models.URLField("ссылка на документ", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="created_contracts")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="updated_contracts")

    class Meta:
        verbose_name = "договор"
        verbose_name_plural = "договоры"
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(fields=["status"], condition=Q(status="active"), name="one_active_contract"),
            models.UniqueConstraint(fields=["status"], condition=Q(status="draft"), name="one_draft_contract"),
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="contract_dates_ordered"),
        ]

    def __str__(self):
        return f"{self.number} — {self.name}"


class ContractServiceTerm(TimeStampedModel):
    class AccountingMode(models.TextChoices):
        QUANTITATIVE = "quantitative", "Количественный"
        NAMED = "named", "Поименный"
        MIXED = "mixed", "Смешанный"
        NONE = "none", "Без контроля"

    class ToleranceType(models.TextChoices):
        PERCENT = "percent", "Процент"
        ABSOLUTE = "absolute", "Абсолютное"

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="service_terms", verbose_name="договор")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="contract_terms", verbose_name="услуга")
    metric_category = models.ForeignKey(ServiceMetricCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="contract_terms", verbose_name="категория учета")
    line_description = models.CharField("описание позиции", max_length=255, blank=True)
    location = models.CharField("место оказания", max_length=255, blank=True)
    unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, null=True, blank=True, related_name="contract_terms", verbose_name="единица")
    accounting_mode = models.CharField("способ учета", max_length=16, choices=AccountingMode)
    contracted_quantity = models.DecimalField("договорное количество", max_digits=14, decimal_places=3, null=True, blank=True)
    tolerance_type = models.CharField("тип допуска", max_length=16, choices=ToleranceType, default=ToleranceType.ABSOLUTE)
    tolerance_value = models.DecimalField("допуск", max_digits=10, decimal_places=2, default=Decimal("0"))
    quantitative_reserve = models.PositiveIntegerField("количественный резерв", null=True, blank=True)
    notes = models.TextField("примечание", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="created_contract_terms")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="updated_contract_terms")

    class Meta:
        verbose_name = "условие услуги договора"
        verbose_name_plural = "условия услуг договора"
        constraints = [models.UniqueConstraint(fields=["contract", "metric_category"], condition=Q(metric_category__isnull=False), name="unique_contract_metric_category")]
        indexes = [models.Index(fields=["contract", "accounting_mode"])]

    def clean(self):
        quantity_required = self.accounting_mode in {self.AccountingMode.QUANTITATIVE, self.AccountingMode.MIXED}
        if quantity_required and self.contracted_quantity is None:
            raise ValidationError("Для количественного или смешанного учета укажите договорное количество.")
        if not quantity_required and self.contracted_quantity is not None:
            raise ValidationError("Договорное количество допустимо только для количественного или смешанного учета.")
        if self.metric_category and self.unit and self.metric_category.unit_id != self.unit_id:
            raise ValidationError("Единица позиции должна совпадать с единицей категории учета.")

    @property
    def allowed_upper_limit(self):
        if self.contracted_quantity is None:
            return None
        if self.tolerance_type == self.ToleranceType.PERCENT:
            return Decimal(self.contracted_quantity) * (Decimal("1") + self.tolerance_value / Decimal("100"))
        return Decimal(self.contracted_quantity) + self.tolerance_value

    def __str__(self):
        return f"{self.contract} / {self.service}"


class ContractListImport(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        COMPLETED = "completed", "Завершен"
        FAILED = "failed", "Ошибка"

    term = models.ForeignKey(ContractServiceTerm, on_delete=models.CASCADE, related_name="imports", verbose_name="условие")
    original_filename = models.CharField("имя файла", max_length=255)
    file_hash = models.CharField("SHA-256", max_length=64)
    raw_csv = models.TextField("исходный CSV")
    status = models.CharField("статус", max_length=16, choices=Status, default=Status.PENDING)
    total_rows = models.PositiveIntegerField("строк", default=0)
    matched_rows = models.PositiveIntegerField("сопоставлено", default=0)
    unmatched_rows = models.PositiveIntegerField("не сопоставлено", default=0)
    ambiguous_rows = models.PositiveIntegerField("неоднозначно", default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="contract_imports")

    class Meta:
        verbose_name = "импорт договорного перечня"
        verbose_name_plural = "импорты договорных перечней"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.term} ({self.original_filename})"


class NamedContractPosition(TimeStampedModel):
    class MatchStatus(models.TextChoices):
        MATCHED = "matched", "Сопоставлено"
        UNMATCHED = "unmatched", "Не сопоставлено"
        AMBIGUOUS = "ambiguous", "Неоднозначно"
        IGNORED = "ignored", "Игнорируется"

    term = models.ForeignKey(ContractServiceTerm, on_delete=models.CASCADE, related_name="named_positions", verbose_name="условие")
    source_identifier = models.CharField("исходный идентификатор", max_length=255)
    source_name = models.CharField("исходное наименование", max_length=255, blank=True)
    source_data = models.JSONField("исходные данные", default=dict, blank=True)
    instance = models.ForeignKey(Instance, on_delete=models.SET_NULL, null=True, blank=True, related_name="contract_positions", verbose_name="экземпляр")
    match_status = models.CharField("состояние сопоставления", max_length=16, choices=MatchStatus, default=MatchStatus.UNMATCHED)
    comment = models.TextField("комментарий", blank=True)
    import_batch = models.ForeignKey(ContractListImport, on_delete=models.SET_NULL, null=True, blank=True, related_name="positions", verbose_name="пакет импорта")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="created_contract_positions")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="updated_contract_positions")

    class Meta:
        verbose_name = "поименная договорная позиция"
        verbose_name_plural = "поименные договорные позиции"
        indexes = [models.Index(fields=["term", "match_status"]), models.Index(fields=["source_identifier"])]
        constraints = [models.UniqueConstraint(fields=["term", "instance"], condition=Q(instance__isnull=False, match_status="matched"), name="unique_matched_instance_per_term")]

    def clean(self):
        if self.match_status == self.MatchStatus.MATCHED and not self.instance:
            raise ValidationError("Сопоставленная позиция должна иметь экземпляр.")
        if self.match_status != self.MatchStatus.MATCHED and self.instance:
            raise ValidationError("Ссылка на экземпляр допустима только у сопоставленной позиции.")

    def __str__(self):
        return f"{self.term}: {self.source_identifier}"


class ContractActualSnapshot(TimeStampedModel):
    contract = models.OneToOneField(Contract, on_delete=models.CASCADE, related_name="actual_snapshot", verbose_name="договор")
    captured_at = models.DateTimeField("зафиксирован", auto_now_add=True)
    captured_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="captured_contract_snapshots", verbose_name="зафиксировал")

    class Meta:
        verbose_name = "снимок актуального состояния договора"
        verbose_name_plural = "снимки актуального состояния договоров"


class ContractActualSnapshotService(TimeStampedModel):
    snapshot = models.ForeignKey(ContractActualSnapshot, on_delete=models.CASCADE, related_name="services", verbose_name="снимок")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="actual_snapshot_services", verbose_name="услуга")
    contract_term = models.OneToOneField(ContractServiceTerm, on_delete=models.SET_NULL, null=True, blank=True, related_name="actual_snapshot_service", verbose_name="условие договора")
    metric_category = models.ForeignKey(ServiceMetricCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="snapshot_services", verbose_name="категория учета")
    service_code = models.CharField("код услуги", max_length=64, blank=True)
    service_name = models.CharField("наименование услуги", max_length=255)
    accounting_mode = models.CharField("способ учета", max_length=16, choices=ContractServiceTerm.AccountingMode.choices)
    actual_quantity = models.DecimalField("актуальное количество", max_digits=14, decimal_places=3)

    class Meta:
        verbose_name = "услуга в снимке договора"
        verbose_name_plural = "услуги в снимке договора"
        constraints = [models.UniqueConstraint(fields=["snapshot", "metric_category"], condition=Q(metric_category__isnull=False), name="contracts_snapshot_category_unique")]


class ContractActualSnapshotInstance(TimeStampedModel):
    snapshot_service = models.ForeignKey(ContractActualSnapshotService, on_delete=models.CASCADE, related_name="instances", verbose_name="услуга снимка")
    instance = models.ForeignKey(Instance, on_delete=models.SET_NULL, null=True, blank=True, related_name="actual_snapshot_instances", verbose_name="экземпляр")
    catalog_code = models.CharField("системный код", max_length=128)
    name = models.CharField("наименование", max_length=255)
    instance_type_name = models.CharField("тип", max_length=255, blank=True)
    glpi_inventory_number = models.CharField("инвентарный номер GLPI", max_length=255, blank=True)
    glpi_serial_number = models.CharField("серийный номер GLPI", max_length=255, blank=True)
    glpi_location = models.CharField("местоположение GLPI", max_length=255, blank=True)
    glpi_external_id = models.CharField("внешний ID GLPI", max_length=255, blank=True)

    class Meta:
        verbose_name = "экземпляр в снимке договора"
        verbose_name_plural = "экземпляры в снимке договора"
        constraints = [models.UniqueConstraint(fields=["snapshot_service", "catalog_code"], name="contracts_snapshot_instance_unique")]
