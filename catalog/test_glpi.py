from datetime import date
from unittest.mock import Mock, patch
from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from catalog.glpi import GlpiClient, GlpiDisabledError, GlpiError, normalize_computer
from catalog.glpi_sync import sync_glpi_reference
from catalog.models import ExternalReference, GlpiComputerSnapshot, Instance, InstanceType


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import HTTPError
            error = HTTPError()
            error.response = self
            raise error


PAYLOAD = {
    "id": 2713, "name": "srv-0002400", "comment": "Esxi4", "serial": None, "otherserial": "ИТ-0002400", "uuid": "uuid-1",
    "date_creation": "2023-12-04T15:31:48+03:00", "date_mod": "2024-09-20T15:50:06+03:00", "last_inventory_update": None,
    "last_boot": "2022-05-27T13:28:39+03:00", "status": {"id": 1, "name": "Активно"}, "entity": {"name": "Атомфлот"},
    "manufacturer": {"name": "DEPO"}, "location": {"name": "Серверная"}, "type": {"name": "Физический сервер"},
    "model": {"name": "X8DTL"}, "autoupdatesystem": {"name": "GLPI Native Inventory"},
}


@override_settings(GLPI_ENABLED=True, GLPI_BASE_URL="https://glpi.test", GLPI_API_VERSION="v2.3", GLPI_CLIENT_ID="client", GLPI_CLIENT_SECRET="secret", GLPI_USERNAME="user", GLPI_PASSWORD="password", GLPI_CA_BUNDLE="", GLPI_TIMEOUT_SECONDS=5)
class GlpiClientTests(TestCase):
    def test_token_is_reused_and_computer_is_normalized(self):
        session = Mock()
        session.post.return_value = FakeResponse({"access_token": "top-secret-token", "expires_in": 3600})
        session.get.return_value = FakeResponse(PAYLOAD)
        client = GlpiClient(session=session)
        first = client.get_computer(2713)
        second = client.get_computer(2713)
        self.assertEqual(session.post.call_count, 1)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(first.inventory_number, "ИТ-0002400")
        self.assertIsNone(first.serial_number)
        self.assertEqual(second.computer_type, "Физический сервер")
        self.assertTrue(session.post.call_args.kwargs["verify"])

    def test_disabled_and_errors_do_not_disclose_secrets(self):
        with self.settings(GLPI_ENABLED=False):
            with self.assertRaises(GlpiDisabledError):
                GlpiClient().get_computer(1)
        session = Mock()
        session.post.return_value = FakeResponse({"error": "bad credentials"}, 401)
        with self.assertRaises(GlpiError) as caught:
            GlpiClient(session=session).get_computer(1)
        self.assertNotIn("secret", str(caught.exception).lower())
        self.assertNotIn("password", str(caught.exception).lower())
        self.assertNotIn("token", str(caught.exception).lower())

    def test_normalizes_nested_and_null_values(self):
        computer = normalize_computer(PAYLOAD)
        self.assertEqual(computer.manufacturer, "DEPO")
        self.assertIsNone(computer.serial_number)
        self.assertIsNone(computer.last_inventory_update)

    def test_tls_verification_can_be_explicitly_disabled(self):
        with self.settings(GLPI_TLS_VERIFY=False):
            self.assertFalse(GlpiClient().verify)


class GlpiSyncTests(TestCase):
    def setUp(self):
        self.kind = InstanceType.objects.create(name="Сервер")
        self.instance = Instance.objects.create(name="Каталожное имя", instance_type=self.kind, notes="ручная заметка")
        self.reference = ExternalReference.objects.create(instance=self.instance, source_system="glpi", external_object_type="Computer", external_id="2713")

    @patch("catalog.glpi_sync.get_glpi_client")
    def test_sync_preserves_catalog_fields_and_updates_snapshot(self, get_client):
        get_client.return_value.get_computer.return_value = normalize_computer(PAYLOAD)
        sync_glpi_reference(self.reference)
        self.instance.refresh_from_db()
        self.reference.refresh_from_db()
        snapshot = self.reference.glpi_computer
        self.assertEqual(self.instance.name, "Каталожное имя")
        self.assertEqual(self.instance.notes, "ручная заметка")
        self.assertEqual(snapshot.external_name, "srv-0002400")
        self.assertEqual(snapshot.inventory_number, "ИТ-0002400")
        self.assertEqual(self.reference.last_sync_status, "success")

    @patch("catalog.glpi_sync.get_glpi_client")
    def test_error_preserves_existing_snapshot(self, get_client):
        GlpiComputerSnapshot.objects.create(reference=self.reference, external_name="старое имя")
        get_client.return_value.get_computer.side_effect = GlpiError("Сеть недоступна")
        with self.assertRaises(GlpiError):
            sync_glpi_reference(self.reference)
        self.reference.refresh_from_db()
        self.assertEqual(self.reference.glpi_computer.external_name, "старое имя")
        self.assertEqual(self.reference.last_sync_status, "error")

    def test_sync_view_requires_change_permission_and_reference(self):
        user = User.objects.create_user("reader", password="test")
        self.client.force_login(user)
        response = self.client.post(f"/instances/{self.instance.pk}/sync-glpi/")
        self.assertEqual(response.status_code, 403)
        user.user_permissions.add(Permission.objects.get(codename="change_instance"))
        response = self.client.post(f"/instances/{self.instance.pk}/sync-glpi/", follow=True)
        self.assertContains(response, "Данные GLPI")

    def test_sync_view_reports_missing_external_reference(self):
        self.reference.delete()
        user = User.objects.create_user("editor", password="test")
        user.user_permissions.add(Permission.objects.get(codename="change_instance"))
        self.client.force_login(user)
        response = self.client.post(f"/instances/{self.instance.pk}/sync-glpi/", follow=True)
        self.assertContains(response, "внешняя ссылка GLPI Computer")
