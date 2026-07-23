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
    code = models.CharField("код", max_length=64, unique=True)
    name = models.CharField("наименование", max_length=255)
    is_active = models.BooleanField("активен", default=True)

    class Meta:
        verbose_name = "тип экземпляра"
        verbose_name_plural = "типы экземпляров"
        ordering = ["name"]
        indexes = [models.Index(fields=["is_active", "code"])]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Instance(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        INACTIVE = "inactive", "Неактивен"
        RETIRED = "retired", "Выведен из эксплуатации"

    class Source(models.TextChoices):
        MANUAL = "manual", "Вручную"

    catalog_code = models.CharField("каталожный код", max_length=128, unique=True)
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
        return f"{self.catalog_code} — {self.name}"


class Service(TimeStampedModel):
    class AccountingMode(models.TextChoices):
        QUANTITATIVE = "quantitative", "Количественный"
        NAMED = "named", "Поименный"
        MIXED = "mixed", "Смешанный"
        NONE = "none", "Без контроля"

    code = models.CharField("код", max_length=64, unique=True)
    name = models.CharField("наименование", max_length=255)
    description = models.TextField("описание", blank=True)
    is_active = models.BooleanField("активна", default=True)
    default_accounting_mode = models.CharField("способ учета по умолчанию", max_length=16, choices=AccountingMode, default=AccountingMode.NONE)

    class Meta:
        verbose_name = "услуга"
        verbose_name_plural = "услуги"
        ordering = ["code"]
        indexes = [models.Index(fields=["is_active", "code"])]

    def __str__(self):
        return f"{self.code} — {self.name}"


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

