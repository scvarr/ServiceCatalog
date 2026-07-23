from datetime import date
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from .models import ExternalReference, GlpiComputerSnapshot, Instance, InstanceType, ListViewPreference, Service, ServiceMembership


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


class CatalogListViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="reader", password="password")
        self.other_user = get_user_model().objects.create_user(username="other", password="password")
        self.client.force_login(self.user)
        self.server_type = InstanceType.objects.create(name="Сервер")
        self.workstation_type = InstanceType.objects.create(name="Рабочая станция")
        self.instance = Instance.objects.create(name="srv-main", instance_type=self.server_type, notes="основной сервер")
        self.service = Service.objects.create(name="Инфраструктура", description="Серверная услуга")
        ServiceMembership.objects.create(service=self.service, instance=self.instance)

    def test_service_default_columns_hide_code_and_name_links_to_detail(self):
        response = self.client.get(reverse("catalog:service_list"))
        self.assertContains(response, "<th>Наименование</th>", html=True)
        self.assertContains(response, "<th>Экземпляров</th>", html=True)
        self.assertNotContains(response, "<th>Код</th>", html=True)
        self.assertContains(response, reverse("catalog:service_detail", args=[self.service.pk]))

    def test_service_searches_code_and_related_instance_without_duplicates(self):
        response = self.client.get(reverse("catalog:service_list"), {"q": self.service.code})
        self.assertContains(response, self.service.name)
        response = self.client.get(reverse("catalog:service_list"), {"q": self.instance.catalog_code})
        self.assertContains(response, self.service.name)
        self.assertEqual(list(response.context["page_obj"].object_list), [self.service])

    def test_service_counts_only_active_memberships(self):
        retired = Instance.objects.create(name="retired", instance_type=self.server_type)
        ServiceMembership.objects.create(
            service=self.service,
            instance=retired,
            status=ServiceMembership.Status.EXCLUDED,
            included_at=date(2026, 1, 1),
            excluded_at=date(2026, 2, 1),
        )
        response = self.client.get(reverse("catalog:service_list"))
        self.assertEqual(response.context["page_obj"].object_list[0].member_count, 1)

    def test_instance_searches_related_service_and_hidden_code(self):
        response = self.client.get(reverse("catalog:instance_list"), {"q": self.instance.catalog_code})
        self.assertContains(response, self.instance.name)
        self.assertNotContains(response, "<th>Код</th>", html=True)
        response = self.client.get(reverse("catalog:instance_list"), {"q": self.service.name})
        self.assertContains(response, self.instance.name)

    def test_instance_filters_and_page_size_are_preserved_in_pagination_links(self):
        for number in range(30):
            Instance.objects.create(name=f"srv-{number}", instance_type=self.server_type)
        response = self.client.get(
            reverse("catalog:instance_list"),
            {"q": "srv", "type": self.server_type.pk, "status": "active", "page_size": 25},
        )
        self.assertEqual(response.context["page_obj"].paginator.per_page, 25)
        self.assertContains(response, f"q=srv&amp;type={self.server_type.pk}&amp;status=active&amp;page_size=25&amp;page=2")

    def test_invalid_page_size_falls_back_to_default_and_invalid_page_is_safe(self):
        response = self.client.get(reverse("catalog:service_list"), {"page_size": "999", "page": "wrong"})
        self.assertEqual(response.context["page_obj"].paginator.per_page, 25)
        self.assertEqual(response.context["page_obj"].number, 1)

    def test_preference_saves_allowed_columns_and_is_user_specific(self):
        url = reverse("catalog:service_list")
        response = self.client.post(
            url,
            {
                "action": "save_preferences",
                "visible_columns": ["name", "code", "unknown"],
                "page_size": "50",
            },
        )
        self.assertRedirects(response, f"{url}?page_size=50")
        preference = ListViewPreference.objects.get(user=self.user, page_key="service_list")
        self.assertEqual(preference.visible_columns, ["name", "code"])
        self.assertEqual(preference.page_size, 50)
        response = self.client.get(url)
        self.assertContains(response, "<th>Код</th>", html=True)
        self.client.force_login(self.other_user)
        response = self.client.get(url)
        self.assertNotContains(response, "<th>Код</th>", html=True)

    def test_required_name_column_cannot_be_disabled_and_reset_restores_defaults(self):
        url = reverse("catalog:instance_list")
        self.client.post(url, {"action": "save_preferences", "visible_columns": ["catalog_code"], "page_size": "100"})
        preference = ListViewPreference.objects.get(user=self.user, page_key="instance_list")
        self.assertEqual(preference.visible_columns, ["name", "catalog_code"])
        response = self.client.post(url, {"action": "reset_preferences"})
        self.assertRedirects(response, url)
        self.assertFalse(ListViewPreference.objects.filter(user=self.user, page_key="instance_list").exists())
        response = self.client.get(url)
        self.assertContains(response, "<th>Тип</th>", html=True)

    def test_page_size_update_keeps_saved_columns(self):
        url = reverse("catalog:service_list")
        self.client.post(url, {"action": "save_preferences", "visible_columns": ["name", "code"], "page_size": "25"})
        response = self.client.post(url, {"action": "save_page_size", "page_size": "100"})
        self.assertRedirects(response, f"{url}?page_size=100")
        preference = ListViewPreference.objects.get(user=self.user, page_key="service_list")
        self.assertEqual(preference.visible_columns, ["name", "code"])
        self.assertEqual(preference.page_size, 100)

    def test_lists_require_login(self):
        self.client.logout()
        response = self.client.get(reverse("catalog:service_list"))
        self.assertEqual(response.status_code, 302)

    def test_service_membership_list_has_search_pagination_and_own_columns(self):
        for number in range(30):
            instance = Instance.objects.create(name=f"member-{number}", instance_type=self.server_type)
            ServiceMembership.objects.create(service=self.service, instance=instance)
        url = reverse("catalog:service_detail", args=[self.service.pk])
        response = self.client.get(url, {"q": "member", "page_size": 25})
        self.assertEqual(response.context["page_obj"].paginator.count, 30)
        self.assertNotContains(response, "<th>Код</th>", html=True)
        self.assertContains(response, "<th>Тип</th>", html=True)
        self.assertContains(response, "q=member&amp;page_size=25&amp;page=2")
        self.client.post(
            url,
            {"action": "save_preferences", "visible_columns": ["name", "catalog_code"], "page_size": "50"},
        )
        preference = ListViewPreference.objects.get(user=self.user, page_key="service_membership_list")
        self.assertEqual(preference.visible_columns, ["name", "catalog_code"])

    def test_glpi_data_is_a_configurable_table(self):
        reference = ExternalReference.objects.create(
            instance=self.instance,
            source_system="glpi",
            external_object_type="Computer",
            external_id="2713",
        )
        GlpiComputerSnapshot.objects.create(reference=reference, external_name="srv-main", inventory_number="INV-01")
        url = reverse("catalog:instance_detail", args=[self.instance.pk])
        response = self.client.get(url)
        self.assertContains(response, "<th>Имя в GLPI</th>", html=True)
        self.assertContains(response, "<th>Инвентарный номер</th>", html=True)
        self.assertNotContains(response, "<th>Серийный номер</th>", html=True)
        self.client.post(
            url,
            {"action": "save_preferences", "visible_columns": ["serial_number", "external_name"], "page_size": "25"},
        )
        preference = ListViewPreference.objects.get(user=self.user, page_key="glpi_computer_data")
        self.assertEqual(preference.visible_columns, ["external_name", "serial_number"])
