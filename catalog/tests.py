from datetime import date
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from .models import Instance, InstanceType, Service, ServiceMembership


class CatalogModelTests(TestCase):
    def setUp(self):
        self.instance_type = InstanceType.objects.create(name="Сервер")
        self.instance = Instance.objects.create(name="srv-001", instance_type=self.instance_type)
        self.service = Service.objects.create(name="Инфраструктура")

    def test_system_codes_are_generated(self):
        self.assertEqual(self.instance.catalog_code, f"INS-{self.instance.pk:06d}")
        self.assertEqual(self.service.code, f"SVC-{self.service.pk:06d}")

    def test_only_one_active_membership_per_pair(self):
        ServiceMembership.objects.create(service=self.service, instance=self.instance, included_at=date(2026, 1, 1))
        with self.assertRaises(IntegrityError):
            ServiceMembership.objects.create(service=self.service, instance=self.instance, included_at=date(2026, 2, 1))

    def test_excluded_membership_requires_date(self):
        membership = ServiceMembership(service=self.service, instance=self.instance, status="excluded")
        with self.assertRaises(ValidationError):
            membership.clean()
