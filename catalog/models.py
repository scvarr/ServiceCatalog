from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class InstanceType(TimeStampedModel):
    name = models.CharField("наименование", max_length=255)
    is_active = models.BooleanField("активен", default=True)

    class Meta:
        verbose_name = "тип экземпляра"
        verbose_name_plural = "типы экземпляров"
        ordering = ["name"]
        indexes = [models.Index(fields=["is_active", "name"], name="catalog_type_active_name_idx")]

    def __str__(self):
        return self.name


class Instance(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        INACTIVE = "inactive", "Неактивен"
        RETIRED = "retired", "Выведен из эксплуатации"

    class Source(models.TextChoices):
        MANUAL = "manual", "Вручную"

    catalog_code = models.CharField("системный код", max_length=128, unique=True, null=True, blank=True, editable=False)
    name = models.CharField("наименование", max_length=255)
    instance_type = models.ForeignKey(InstanceType, on_delete=models.PROTECT, related_name="instances", verbose_name="тип")
    status = models.CharField("состояние", max_length=16, choices=Status, default=Status.ACTIVE)
    source = models.CharField("источник", max_length=32, choices=Source, default=Source.MANUAL)
    notes = models.TextField("примечание", blank=True)

    class Meta:
        verbose_name = "экземпляр"
        verbose_name_plural = "экземпляры"
        ordering = ["catalog_code"]
        indexes = [models.Index(fields=["instance_type", "status"])]

    def __str__(self):
        return f"{self.catalog_code or self.pk} — {self.name}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.catalog_code:
            self.catalog_code = f"INS-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(catalog_code=self.catalog_code)


class Service(TimeStampedModel):
    class AccountingMode(models.TextChoices):
        QUANTITATIVE = "quantitative", "Количественный"
        NAMED = "named", "Поименный"
        MIXED = "mixed", "Смешанный"
        NONE = "none", "Без контроля"

    code = models.CharField("системный код", max_length=64, unique=True, null=True, blank=True, editable=False)
    name = models.CharField("наименование", max_length=255)
    description = models.TextField("описание", blank=True)
    is_active = models.BooleanField("активна", default=True)
    default_accounting_mode = models.CharField("способ учета по умолчанию", max_length=16, choices=AccountingMode, default=AccountingMode.NONE)

    class Meta:
        verbose_name = "услуга"
        verbose_name_plural = "услуги"
        ordering = ["code"]
        indexes = [models.Index(fields=["is_active", "name"], name="catalog_svc_active_name_idx")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.code:
            self.code = f"SVC-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(code=self.code)


class UnitOfMeasure(TimeStampedModel):
    code = models.SlugField("код", max_length=32, unique=True)
    name = models.CharField("наименование", max_length=100)
    symbol = models.CharField("сокращение", max_length=16, unique=True)
    is_active = models.BooleanField("активна", default=True)

    class Meta:
        verbose_name = "единица измерения"
        verbose_name_plural = "единицы измерения"
        ordering = ["name"]

    def __str__(self):
        return self.symbol


class ServiceMetricCategory(TimeStampedModel):
    class ActualValueMethod(models.TextChoices):
        MEMBER_COUNT = "member_count", "Количество экземпляров"
        MANUAL = "manual", "Ручной показатель"

    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="metric_categories", verbose_name="услуга")
    code = models.SlugField("код", max_length=64)
    name = models.CharField("наименование", max_length=255)
    location = models.CharField("место оказания", max_length=255, blank=True)
    unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name="metric_categories", verbose_name="единица")
    actual_value_method = models.CharField("метод актуального значения", max_length=32, choices=ActualValueMethod, default=ActualValueMethod.MANUAL)
    is_active = models.BooleanField("активна", default=True)
    notes = models.TextField("примечание", blank=True)

    class Meta:
        verbose_name = "категория учета услуги"
        verbose_name_plural = "категории учета услуг"
        ordering = ["service", "name"]
        constraints = [models.UniqueConstraint(fields=["service", "code"], name="catalog_metric_category_unique")]

    def __str__(self):
        return f"{self.service} — {self.name}"


class ActualServiceMetric(TimeStampedModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Вручную"
        CALCULATED = "calculated", "Рассчитано"
        IMPORTED = "imported", "Импортировано"

    category = models.ForeignKey(ServiceMetricCategory, on_delete=models.PROTECT, related_name="actual_metrics", verbose_name="категория учета")
    value = models.DecimalField("значение", max_digits=14, decimal_places=3)
    effective_at = models.DateTimeField("актуально на")
    source = models.CharField("источник", max_length=16, choices=Source, default=Source.MANUAL)
    comment = models.TextField("комментарий", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="created_actual_metrics", verbose_name="создал")

    class Meta:
        verbose_name = "актуальный показатель услуги"
        verbose_name_plural = "история актуальных показателей"
        ordering = ["-effective_at", "-created_at"]
        indexes = [models.Index(fields=["category", "-effective_at"])]


class ServerProfile(TimeStampedModel):
    class CommissioningPrecision(models.TextChoices):
        EXACT = "exact", "Точная дата"
        MONTH = "month", "Известен месяц"
        YEAR = "year", "Известен год"
        APPROXIMATE = "approximate", "Приблизительно"
        UNKNOWN = "unknown", "Неизвестно"

    class Level(models.TextChoices):
        UNKNOWN = "unknown", "Не определено"
        LOW = "low", "Низкий"
        MEDIUM = "medium", "Средний"
        HIGH = "high", "Высокий"
        CRITICAL = "critical", "Критический"

    instance = models.OneToOneField(Instance, on_delete=models.CASCADE, related_name="server_profile", verbose_name="экземпляр")
    manufacturer = models.CharField("производитель", max_length=255, blank=True)
    model = models.CharField("модель", max_length=255, blank=True)
    cpu_summary = models.CharField("процессор", max_length=500, blank=True)
    core_count = models.PositiveIntegerField("ядер", null=True, blank=True)
    memory_total_gb = models.DecimalField("память, ГБ", max_digits=10, decimal_places=2, null=True, blank=True)
    storage_summary = models.TextField("дисковая конфигурация", blank=True)
    raid_controller = models.CharField("RAID-контроллер", max_length=255, blank=True)
    hypervisor = models.CharField("ОС / гипервизор", max_length=255, blank=True)
    technical_condition = models.CharField("техническое состояние", max_length=16, choices=Level, default=Level.UNKNOWN)
    criticality = models.CharField("критичность", max_length=16, choices=Level, default=Level.UNKNOWN)
    risk_level = models.CharField("уровень риска", max_length=16, choices=Level, default=Level.UNKNOWN)
    risk_reason = models.TextField("причина риска", blank=True)
    risk_recommendation = models.TextField("рекомендация", blank=True)
    replacement_year = models.PositiveSmallIntegerField("плановый год замены", null=True, blank=True)
    spare_parts_available = models.BooleanField("есть запасные части", null=True, blank=True)
    commissioned_on = models.DateField("ввод в эксплуатацию", null=True, blank=True)
    commissioned_year = models.PositiveSmallIntegerField("год ввода", null=True, blank=True)
    commissioned_month = models.PositiveSmallIntegerField("месяц ввода", null=True, blank=True)
    commissioning_precision = models.CharField("точность даты ввода", max_length=16, choices=CommissioningPrecision, default=CommissioningPrecision.UNKNOWN)
    commissioning_comment = models.TextField("комментарий к дате ввода", blank=True)

    class Meta:
        verbose_name = "паспорт сервера"
        verbose_name_plural = "паспорта серверов"

    def clean(self):
        if self.commissioning_precision == self.CommissioningPrecision.EXACT and not self.commissioned_on:
            raise ValidationError("Для точной даты укажите дату ввода в эксплуатацию.")
        if self.commissioning_precision == self.CommissioningPrecision.MONTH and not (self.commissioned_year and self.commissioned_month):
            raise ValidationError("Для известного месяца укажите год и месяц.")
        if self.commissioning_precision in {self.CommissioningPrecision.YEAR, self.CommissioningPrecision.APPROXIMATE} and not self.commissioned_year:
            raise ValidationError("Укажите год ввода в эксплуатацию.")

    @property
    def commissioning_display(self):
        if self.commissioning_precision == self.CommissioningPrecision.EXACT and self.commissioned_on:
            return self.commissioned_on.strftime("%d.%m.%Y")
        if self.commissioning_precision == self.CommissioningPrecision.MONTH and self.commissioned_year and self.commissioned_month:
            return f"{self.commissioned_month:02d}.{self.commissioned_year}"
        if self.commissioning_precision == self.CommissioningPrecision.YEAR and self.commissioned_year:
            return str(self.commissioned_year)
        if self.commissioning_precision == self.CommissioningPrecision.APPROXIMATE and self.commissioned_year:
            return f"≈ {self.commissioned_year}"
        return "неизвестно"


class ServiceMembership(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активно"
        EXCLUDED = "excluded", "Исключено"

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="memberships", verbose_name="услуга")
    instance = models.ForeignKey(Instance, on_delete=models.PROTECT, related_name="service_memberships", verbose_name="экземпляр")
    included_at = models.DateField("дата включения", default=timezone.localdate)
    excluded_at = models.DateField("дата исключения", null=True, blank=True)
    status = models.CharField("состояние", max_length=16, choices=Status, default=Status.ACTIVE)
    reason = models.TextField("основание / примечание", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="created_memberships", verbose_name="создал")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="updated_memberships", verbose_name="изменил")

    class Meta:
        verbose_name = "участие экземпляра в услуге"
        verbose_name_plural = "состав услуг"
        ordering = ["service", "-included_at"]
        constraints = [
            models.UniqueConstraint(fields=["service", "instance"], condition=Q(status="active"), name="unique_active_service_membership"),
            models.CheckConstraint(condition=Q(excluded_at__isnull=True) | Q(excluded_at__gte=models.F("included_at")), name="membership_dates_ordered"),
        ]
        indexes = [models.Index(fields=["service", "status", "included_at"]), models.Index(fields=["instance", "status"])]

    def clean(self):
        if self.status == self.Status.ACTIVE and self.excluded_at:
            raise ValidationError("Активное участие не может иметь дату исключения.")
        if self.status == self.Status.EXCLUDED and not self.excluded_at:
            raise ValidationError("Для исключенного участия укажите дату исключения.")

    def __str__(self):
        return f"{self.service}: {self.instance}"

    @property
    def is_current(self):
        return self.status == self.Status.ACTIVE and self.included_at <= timezone.localdate()


class ListViewPreference(models.Model):
    class PageKey(models.TextChoices):
        SERVICE_LIST = "service_list", "Список услуг"
        INSTANCE_LIST = "instance_list", "Список экземпляров"
        SERVICE_MEMBERSHIP_LIST = "service_membership_list", "Состав услуги"
        GLPI_COMPUTER_DATA = "glpi_computer_data", "Данные GLPI"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="list_view_preferences", verbose_name="пользователь")
    page_key = models.CharField("страница", max_length=32, choices=PageKey)
    visible_columns = models.JSONField("видимые столбцы", default=list, blank=True)
    page_size = models.PositiveSmallIntegerField("строк на странице", default=25)

    class Meta:
        verbose_name = "настройка списка"
        verbose_name_plural = "настройки списков"
        constraints = [models.UniqueConstraint(fields=["user", "page_key"], name="catalog_list_preference_unique")]

    def __str__(self):
        return f"{self.user} — {self.get_page_key_display()}"


class ExternalReference(TimeStampedModel):
    class SourceSystem(models.TextChoices):
        GLPI = "glpi", "GLPI"

    class SyncStatus(models.TextChoices):
        PENDING = "pending", "Не синхронизировано"
        SUCCESS = "success", "Успешно"
        ERROR = "error", "Ошибка"

    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name="external_references", verbose_name="экземпляр")
    source_system = models.CharField("внешняя система", max_length=32, choices=SourceSystem)
    external_object_type = models.CharField("тип внешнего объекта", max_length=64)
    external_id = models.CharField("внешний ID", max_length=255)
    external_url = models.URLField("ссылка", blank=True)
    last_synced_at = models.DateTimeField("последняя успешная синхронизация", null=True, blank=True)
    last_sync_status = models.CharField("статус синхронизации", max_length=16, choices=SyncStatus, default=SyncStatus.PENDING)
    last_sync_error = models.CharField("последняя ошибка", max_length=500, blank=True)

    class Meta:
        verbose_name = "внешняя ссылка"
        verbose_name_plural = "внешние ссылки"
        constraints = [models.UniqueConstraint(fields=["source_system", "external_object_type", "external_id"], name="unique_external_object")]
        indexes = [models.Index(fields=["instance", "source_system"], name="cat_ext_inst_src_idx")]

    def __str__(self):
        return f"{self.source_system}: {self.external_object_type} #{self.external_id}"


class GlpiComputerSnapshot(TimeStampedModel):
    reference = models.OneToOneField(ExternalReference, on_delete=models.CASCADE, related_name="glpi_computer", verbose_name="внешняя ссылка")
    external_name = models.CharField("имя в GLPI", max_length=255, blank=True)
    inventory_number = models.CharField("инвентарный номер", max_length=255, blank=True)
    serial_number = models.CharField("серийный номер", max_length=255, blank=True)
    external_uuid = models.CharField("UUID", max_length=255, blank=True)
    external_status = models.CharField("статус GLPI", max_length=255, blank=True)
    manufacturer = models.CharField("производитель", max_length=255, blank=True)
    model = models.CharField("модель", max_length=255, blank=True)
    external_type = models.CharField("тип GLPI", max_length=255, blank=True)
    location = models.CharField("местоположение", max_length=255, blank=True)
    entity_name = models.CharField("сущность", max_length=255, blank=True)
    comment = models.TextField("комментарий GLPI", blank=True)
    inventory_source = models.CharField("источник инвентаризации", max_length=255, blank=True)
    external_created_at = models.DateTimeField("создан в GLPI", null=True, blank=True)
    external_updated_at = models.DateTimeField("изменен в GLPI", null=True, blank=True)
    last_inventory_update = models.DateTimeField("последняя инвентаризация", null=True, blank=True)
    last_boot = models.DateTimeField("последняя загрузка", null=True, blank=True)

    class Meta:
        verbose_name = "данные компьютера GLPI"
        verbose_name_plural = "данные компьютеров GLPI"

    def __str__(self):
        return self.external_name or str(self.reference)


class GlpiImportSession(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        RUNNING = "running", "Выполняется"
        COMPLETED = "completed", "Завершен"
        PARTIAL = "partial", "Частично завершен"
        FAILED = "failed", "Ошибка"

    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name="glpi_import_sessions", verbose_name="экземпляр")
    reference = models.ForeignKey(ExternalReference, on_delete=models.PROTECT, related_name="import_sessions", verbose_name="внешняя ссылка")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="requested_glpi_imports", verbose_name="запросил")
    status = models.CharField("статус", max_length=16, choices=Status, default=Status.PENDING)
    started_at = models.DateTimeField("начат", null=True, blank=True)
    finished_at = models.DateTimeField("завершен", null=True, blank=True)
    normalizer_version = models.CharField("версия нормализатора", max_length=32, default="v1")
    error = models.CharField("ошибка", max_length=500, blank=True)


class GlpiImportPayload(TimeStampedModel):
    session = models.ForeignKey(GlpiImportSession, on_delete=models.CASCADE, related_name="payloads", verbose_name="сессия")
    endpoint_key = models.CharField("ключ endpoint", max_length=64)
    http_status = models.PositiveSmallIntegerField("HTTP-статус", null=True, blank=True)
    payload = models.JSONField("сырой JSON", default=dict, blank=True)
    error = models.CharField("ошибка", max_length=500, blank=True)
    fetched_at = models.DateTimeField("получен", auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "endpoint_key"], name="catalog_glpi_payload_unique")]


class GlpiImportCandidate(TimeStampedModel):
    class Decision(models.TextChoices):
        PENDING = "pending", "Ожидает решения"
        APPLIED = "applied", "Применено"
        SKIPPED = "skipped", "Пропущено"

    session = models.ForeignKey(GlpiImportSession, on_delete=models.CASCADE, related_name="candidates", verbose_name="сессия")
    field_key = models.CharField("поле", max_length=64)
    current_value = models.TextField("текущее значение", blank=True)
    proposed_value = models.TextField("предлагаемое значение", blank=True)
    source = models.CharField("источник", max_length=32, default="glpi")
    rule = models.CharField("правило", max_length=64, default="direct")
    decision = models.CharField("решение", max_length=16, choices=Decision, default=Decision.PENDING)
    applied_at = models.DateTimeField("применено", null=True, blank=True)
    applied_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="applied_glpi_candidates", verbose_name="применил")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "field_key"], name="catalog_glpi_candidate_unique")]
