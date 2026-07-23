from datetime import date
import json
from unittest.mock import Mock, patch
from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from catalog.glpi import GlpiClient, GlpiDisabledError, GlpiError, normalize_computer
from catalog.glpi_import import create_glpi_import, normalize_import_candidates
from catalog.glpi_sync import sync_glpi_reference
from catalog.glpi_diagnostics import build_glpi_diagnostic_archive
from catalog.models import ExternalReference, GlpiComputerSnapshot, GlpiImportPayload, GlpiImportSession, Instance, InstanceType


class FakeResponse:
    def __init__(self, payload, status=200, content_type="application/json"):
        self.payload, self.status_code = payload, status
        self.headers = {"Content-Type": content_type}
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

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

    def test_component_request_uses_documented_computer_path(self):
        session = Mock()
        session.post.return_value = FakeResponse({"access_token": "top-secret-token", "expires_in": 3600})
        session.get.return_value = FakeResponse([])
        GlpiClient(session=session).get_computer_component_payload(2713, "memory")
        self.assertEqual(session.get.call_args.args[0], "https://glpi.test/api.php/v2.3/Assets/Computer/2713/Component/Memory")

    def test_tls_verification_can_be_explicitly_disabled(self):
        with self.settings(GLPI_TLS_VERIFY=False):
            self.assertFalse(GlpiClient().verify)

    def test_api_schema_returns_openapi_document(self):
        session = Mock()
        session.get.return_value = FakeResponse({"openapi": "3.0.0", "paths": {"/Assets/Computer/{id}": {"get": {}}}})
        schema, attempts, documents = GlpiClient(session=session).get_api_schema()
        self.assertEqual(schema["openapi"], "3.0.0")
        self.assertEqual(attempts[0]["path"], "/api.php/doc")
        self.assertEqual(documents, {})

    def test_api_schema_follows_openapi_url_from_documentation_page(self):
        session = Mock()
        missing = FakeResponse({"error": "not found"}, 404)
        documentation = FakeResponse('<script>const ui = SwaggerUIBundle({url: "/api.php/v2.3/schema.json"});</script>', content_type="text/html")
        schema = FakeResponse({"openapi": "3.0.0", "paths": {"/Assets/Computer": {"get": {}}}})
        session.get.side_effect = [documentation, missing, missing, missing, missing, missing, schema]
        result, attempts, documents = GlpiClient(session=session).get_api_schema()
        self.assertEqual(result["openapi"], "3.0.0")
        self.assertIn("api.php-doc", documents)
        self.assertEqual(attempts[-1]["path"], "/api.php/v2.3/schema.json")

    def test_api_schema_follows_url_from_swagger_initializer_script(self):
        session = Mock()
        missing = FakeResponse({"error": "not found"}, 404)
        documentation = FakeResponse('<script src="/api.php/doc/swagger-initializer.js"></script>', content_type="text/html")
        initializer = FakeResponse('SwaggerUIBundle({url: "/api.php/openapi.json"});', content_type="application/javascript")
        schema = FakeResponse({"openapi": "3.0.0", "paths": {"/Assets": {"get": {}}}})
        session.get.side_effect = [documentation, missing, missing, missing, missing, missing, initializer, schema]
        result, attempts, documents = GlpiClient(session=session).get_api_schema()
        self.assertEqual(result["openapi"], "3.0.0")
        self.assertIn("api.php-doc-swagger-initializer.js", documents)
        self.assertEqual(attempts[-1]["path"], "/api.php/openapi.json")

    def test_api_schema_creates_web_session_when_documentation_is_login_page(self):
        session = Mock()
        login_page = FakeResponse('<input name="_glpi_csrf_token" value="csrf"><select><option value="ldap-1" selected>LDAP</option></select><input name="login_name">', content_type="text/html")
        session.get.side_effect = [login_page, login_page, FakeResponse({"openapi": "3.0.0", "paths": {"/Assets": {"get": {}}}})]
        session.post.return_value = FakeResponse("<html>logged in</html>", content_type="text/html")
        schema, attempts, _ = GlpiClient(session=session).get_api_schema()
        self.assertEqual(schema["openapi"], "3.0.0")
        self.assertTrue(attempts[0]["login_required"])
        self.assertEqual(session.post.call_args.kwargs["data"]["auth"], "ldap-1")

    @patch("catalog.glpi_diagnostics.get_glpi_client")
    def test_diagnostic_archive_contains_redacted_sample_and_endpoint_list(self, get_client):
        client = get_client.return_value
        client.get_computer_payload.return_value = PAYLOAD
        client.get_api_schema.return_value = ({"paths": {"/Assets/Computer/{id}": {"get": {}}, "/Assets/Computer": {"post": {}}}}, [], {"api.php-doc": "<html>docs</html>"})
        reference = Mock(external_id="2713")
        import zipfile
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(build_glpi_diagnostic_archive(reference))) as package:
            self.assertIn("openapi.json", package.namelist())
            self.assertIn("documentation/api.php-doc.html", package.namelist())
            self.assertIn("/Assets/Computer/{id}", package.read("endpoints.json").decode())
            self.assertIn("<redacted>", package.read("computer.sample.json").decode())


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


class GlpiImportTests(TestCase):
    def setUp(self):
        kind = InstanceType.objects.create(name="Сервер")
        self.instance = Instance.objects.create(name="srv-import", instance_type=kind)
        self.reference = ExternalReference.objects.create(instance=self.instance, source_system="glpi", external_object_type="Computer", external_id="2713")

    def test_normalizes_server_profile_candidates_from_components(self):
        candidates = normalize_import_candidates({
            "computer": {"manufacturer": {"name": "DEPO"}, "model": {"name": "X8DTL"}},
            "processor": [{"processor": {"name": "Xeon E5"}, "nbcores": 8}, {"processor": {"name": "Xeon E5"}, "nbcores": 8}],
            "memory": [{"size": 32768}, {"size": 32768}],
            "controller": [{"controller": {"name": "PERC H730"}}],
            "hard_drive": [{"hard_drive": {"name": "SSD"}, "capacity": 960000}],
            "os_installation": [{"operatingsystem": {"name": "VMware ESXi"}, "version": {"name": "8.0"}}],
        })
        self.assertEqual(candidates["cpu_summary"][0], "2 × Xeon E5")
        self.assertEqual(candidates["core_count"][0], "16")
        self.assertEqual(candidates["memory_total_gb"][0], "64")
        self.assertIn("PERC H730", candidates["raid_controller"][0])
        self.assertIn("VMware ESXi 8.0", candidates["hypervisor"][0])

    @patch("catalog.glpi_import.get_glpi_client")
    def test_import_keeps_successful_payloads_when_one_component_fails(self, get_client):
        client = get_client.return_value
        client.get_computer_payload.return_value = PAYLOAD
        client.get_computer_component_payload.side_effect = lambda _, key: (_ for _ in ()).throw(GlpiError("HTTP 403")) if key == "memory" else []
        client.get_computer_related_payload.return_value = []
        session = create_glpi_import(self.reference)
        self.assertEqual(session.status, GlpiImportSession.Status.PARTIAL)
        self.assertEqual(GlpiImportPayload.objects.filter(session=session).count(), 9)
        self.assertTrue(GlpiImportPayload.objects.get(session=session, endpoint_key="memory").error)

    @patch("catalog.glpi_import.get_glpi_client")
    def test_import_persists_component_http_status(self, get_client):
        client = get_client.return_value
        client.get_computer_payload.return_value = PAYLOAD
        client.get_computer_component_payload.side_effect = lambda _, key: (_ for _ in ()).throw(GlpiError("HTTP 403", http_status=403)) if key == "processor" else []
        client.get_computer_related_payload.return_value = []
        session = create_glpi_import(self.reference)
        self.assertEqual(GlpiImportPayload.objects.get(session=session, endpoint_key="processor").http_status, 403)
