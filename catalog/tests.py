from datetime import date
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from .models import Instance, InstanceType, Service, ServiceMembership


class CatalogModelTests(TestCase):
    def setUp(self):
        self.instance_type = InstanceType.objects.create(code="server", name="Сервер")
        self.instance = Instance.objects.create(catalog_code="SRV-001", name="srv-001", instance_type=self.instance_type)
        self.service = Service.objects.create(code="infra", name="Инфраструктура")

    def test_catalog_code_is_unique(self):
        with self.assertRaises(IntegrityError):
            Instance.objects.create(catalog_code="SRV-001", name="duplicate", instance_type=self.instance_type)

    def test_only_one_active_membership_per_pair(self):
        ServiceMembership.objects.create(service=self.service, instance=self.instance, included_at=date(2026, 1, 1))
        with self.assertRaises(IntegrityError):
            ServiceMembership.objects.create(service=self.service, instance=self.instance, included_at=date(2026, 2, 1))

    def test_excluded_membership_requires_date(self):
        membership = ServiceMembership(service=self.service, instance=self.instance, status="excluded")
        with self.assertRaises(ValidationError):
            membership.clean()

