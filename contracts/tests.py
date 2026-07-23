from datetime import date
from django.db import IntegrityError
from django.test import TestCase
from catalog.models import Instance, InstanceType, Service, ServiceMembership
from .models import Contract, ContractServiceTerm, NamedContractPosition
from .services import comparison_for_term, import_csv


class ContractTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(name="Рабочие места")
        self.kind = InstanceType.objects.create(name="ПК")
        self.instance = Instance.objects.create(name="ПК 001", instance_type=self.kind)
        ServiceMembership.objects.create(service=self.service, instance=self.instance)
        self.contract = Contract.objects.create(number="2026-01", name="Договор 2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), status="active")

    def test_only_one_active_contract(self):
        with self.assertRaises(IntegrityError):
            Contract.objects.create(number="2026-02", name="Другой", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), status="active")

    def test_csv_import_preserves_unmatched_rows_and_comparison(self):
        term = ContractServiceTerm.objects.create(contract=self.contract, service=self.service, accounting_mode="named")
        batch = import_csv(term, f"catalog_code,name\n{self.instance.catalog_code},Known\nUNKNOWN,Missing\n", "list.csv")
        self.assertEqual(batch.matched_rows, 1)
        self.assertEqual(batch.unmatched_rows, 1)
        comparison = comparison_for_term(term)
        self.assertEqual(comparison["matched"].count(), 1)
        self.assertEqual(comparison["unmatched"].count(), 1)
        self.assertEqual(comparison["actual_only"].count(), 0)

    def test_matched_position_requires_instance(self):
        term = ContractServiceTerm.objects.create(contract=self.contract, service=self.service, accounting_mode="named")
        position = NamedContractPosition(term=term, source_identifier="INS-000001", match_status="matched")
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            position.clean()
