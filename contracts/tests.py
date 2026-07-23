from datetime import date
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from catalog.models import Instance, InstanceType, Service, ServiceMembership
from .models import Contract, ContractActualSnapshot, ContractServiceTerm, NamedContractPosition
from .services import compare_contract_service_to_actual, comparison_for_term, import_csv, populate_contract_from_actual


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
        draft = Contract.objects.create(number="2026-draft", name="Черновик", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), status="draft")
        term = ContractServiceTerm.objects.create(contract=draft, service=self.service, accounting_mode="named")
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

    def test_quantitative_comparison_uses_inclusive_tolerance_and_shortfall(self):
        term = ContractServiceTerm.objects.create(contract=self.contract, service=self.service, accounting_mode="quantitative", contracted_quantity=1, tolerance_type="absolute", tolerance_value=1)
        second = Instance.objects.create(name="ПК 002", instance_type=self.kind)
        ServiceMembership.objects.create(service=self.service, instance=second)
        self.assertEqual(compare_contract_service_to_actual(term)["status"], "within_tolerance")
        ServiceMembership.objects.filter(instance=self.instance).update(status="excluded", excluded_at=timezone.localdate())
        self.assertEqual(compare_contract_service_to_actual(term)["status"], "match")
        ServiceMembership.objects.filter(instance=second).update(status="excluded", excluded_at=timezone.localdate())
        self.assertEqual(compare_contract_service_to_actual(term)["status"], "shortfall")

    def test_named_comparison_detects_changed_composition_with_equal_count(self):
        draft = Contract.objects.create(number="2026-draft", name="Черновик", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), status="draft")
        term = ContractServiceTerm.objects.create(contract=draft, service=self.service, accounting_mode="named")
        NamedContractPosition.objects.create(term=term, source_identifier=self.instance.catalog_code, source_name=self.instance.name, instance=self.instance, match_status="matched")
        replacement = Instance.objects.create(name="ПК 002", instance_type=self.kind)
        ServiceMembership.objects.create(service=self.service, instance=replacement)
        ServiceMembership.objects.filter(instance=self.instance).update(status="excluded", excluded_at=timezone.localdate())
        result = compare_contract_service_to_actual(term)
        self.assertEqual(result["actual_quantity"], 1)
        self.assertEqual(result["status"], "composition_changed")
        self.assertEqual(result["composition_delta"], "+1 / −1")

    def test_populate_draft_creates_independent_snapshot_and_positions(self):
        draft = Contract.objects.create(number="2026-draft", name="Черновик", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), status="draft")
        self.service.default_accounting_mode = "mixed"; self.service.save()
        snapshot = populate_contract_from_actual(draft)
        self.assertIsInstance(snapshot, ContractActualSnapshot)
        term = draft.service_terms.get(service=self.service)
        self.assertEqual(term.contracted_quantity, 1)
        self.assertEqual(term.named_positions.count(), 1)
        self.instance.name = "Переименован"; self.instance.save()
        snapshot_instance = snapshot.services.get(service=self.service).instances.get()
        self.assertEqual(snapshot_instance.name, "ПК 001")
        with self.assertRaises(ValidationError):
            populate_contract_from_actual(draft)

    def test_active_contract_cannot_be_populated_or_imported(self):
        term = ContractServiceTerm.objects.create(contract=self.contract, service=self.service, accounting_mode="named")
        with self.assertRaises(ValidationError):
            populate_contract_from_actual(self.contract)
        with self.assertRaises(ValueError):
            import_csv(term, "catalog_code\nINS-000001\n", "list.csv")

    def test_contract_summary_and_project_creation_view(self):
        user = get_user_model().objects.create_user(username="contracts", password="password")
        user.user_permissions.add(Permission.objects.get(codename="add_contract"))
        self.client.force_login(user)
        response = self.client.get(reverse("contracts:contract_detail", args=[self.contract.pk]))
        self.assertContains(response, "Сравнение с актуальным состоянием")
        response = self.client.post(reverse("contracts:contract_project_create"), {
            "number": "2026-draft", "name": "Черновик", "start_date": "2026-01-01", "end_date": "2026-12-31", "fill_from_actual": "on",
        })
        self.assertEqual(response.status_code, 302)
        draft = Contract.objects.get(number="2026-draft")
        self.assertTrue(ContractActualSnapshot.objects.filter(contract=draft, captured_by=user).exists())
