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
