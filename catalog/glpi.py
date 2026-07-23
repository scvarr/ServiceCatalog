from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings


class GlpiError(Exception):
    """Safe error suitable for user messages and persisted sync status."""


class GlpiDisabledError(GlpiError):
    pass


@dataclass(frozen=True)
class GlpiComputer:
    id: str
    name: str | None
    inventory_number: str | None
    serial_number: str | None
    uuid: str | None
    status: str | None
    manufacturer: str | None
    model: str | None
    computer_type: str | None
    location: str | None
    entity_name: str | None
    comment: str | None
    inventory_source: str | None
    created_at: datetime | None
    updated_at: datetime | None
    last_inventory_update: datetime | None
    last_boot: datetime | None


def _nested_name(value: Any) -> str | None:
    return value.get("name") if isinstance(value, dict) else None


def _date(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def normalize_computer(payload: dict[str, Any]) -> GlpiComputer:
    return GlpiComputer(
        id=str(payload["id"]), name=payload.get("name"), inventory_number=payload.get("otherserial"),
        serial_number=payload.get("serial"), uuid=payload.get("uuid"), status=_nested_name(payload.get("status")),
        manufacturer=_nested_name(payload.get("manufacturer")), model=_nested_name(payload.get("model")),
        computer_type=_nested_name(payload.get("type")), location=_nested_name(payload.get("location")),
        entity_name=_nested_name(payload.get("entity")), comment=payload.get("comment"),
        inventory_source=_nested_name(payload.get("autoupdatesystem")), created_at=_date(payload.get("date_creation")),
        updated_at=_date(payload.get("date_mod")), last_inventory_update=_date(payload.get("last_inventory_update")),
        last_boot=_date(payload.get("last_boot")),
    )


class GlpiClient:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.access_token: str | None = None
        self.token_expires_at: datetime | None = None

    @property
    def verify(self):
        if not settings.GLPI_TLS_VERIFY:
            return False
        return settings.GLPI_CA_BUNDLE or True

    def _require_config(self):
        if not settings.GLPI_ENABLED:
            raise GlpiDisabledError("Интеграция с GLPI отключена.")
        if not all([settings.GLPI_BASE_URL, settings.GLPI_CLIENT_ID, settings.GLPI_CLIENT_SECRET, settings.GLPI_USERNAME, settings.GLPI_PASSWORD]):
            raise GlpiError("Конфигурация GLPI неполная.")

    def _token(self) -> str:
        self._require_config()
        if self.access_token and self.token_expires_at and self.token_expires_at > datetime.now(timezone.utc):
            return self.access_token
        try:
            response = self.session.post(
                f"{settings.GLPI_BASE_URL}/api.php/token",
                data={"grant_type": "password", "client_id": settings.GLPI_CLIENT_ID, "client_secret": settings.GLPI_CLIENT_SECRET,
                      "username": settings.GLPI_USERNAME, "password": settings.GLPI_PASSWORD, "scope": "api"},
                timeout=settings.GLPI_TIMEOUT_SECONDS, verify=self.verify,
            )
            response.raise_for_status()
            data = response.json()
            token = data.get("access_token")
            if not token:
                raise GlpiError("GLPI не вернул access token.")
            self.access_token = token
            self.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(int(data.get("expires_in", 3600)) - 30, 1))
            return token
        except requests.RequestException as exc:
            raise GlpiError(f"Не удалось получить токен GLPI: {type(exc).__name__}.") from exc
        except (TypeError, ValueError) as exc:
            raise GlpiError("GLPI вернул некорректный ответ токена.") from exc

    def get_computer(self, computer_id: int | str) -> GlpiComputer:
        return normalize_computer(self.get_computer_payload(computer_id))

    def get_computer_payload(self, computer_id: int | str) -> dict[str, Any]:
        token = self._token()
        try:
            response = self.session.get(
                f"{settings.GLPI_BASE_URL}/api.php/{settings.GLPI_API_VERSION}/Assets/Computer/{computer_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=settings.GLPI_TIMEOUT_SECONDS, verify=self.verify,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Computer payload is not an object")
            return payload
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise GlpiError(f"GLPI вернул HTTP {status} при получении компьютера.") from exc
        except requests.RequestException as exc:
            raise GlpiError(f"Не удалось получить компьютер из GLPI: {type(exc).__name__}.") from exc
        except (TypeError, ValueError, KeyError) as exc:
            raise GlpiError("GLPI вернул некорректные данные компьютера.") from exc

    def get_api_schema(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, str]]:
        """Fetch public API docs and the OpenAPI document they reference.

        GLPI intentionally exposes its API documentation before authorization.
        This discovery therefore must not depend on OAuth being configured.
        """
        paths = (
            "/api.php/doc",
            "/api.php/doc/openapi.json",
            f"/api.php/{settings.GLPI_API_VERSION}/doc",
            f"/api.php/{settings.GLPI_API_VERSION}/openapi.json",
            f"/api.php/{settings.GLPI_API_VERSION}/openapi",
        )
        attempts: list[dict[str, Any]] = []
        documents: dict[str, str] = {}
        queued = list(paths)
        visited = set()
        base = urlparse(settings.GLPI_BASE_URL)
        while queued:
            path = queued.pop(0)
            if path in visited:
                continue
            visited.add(path)
            try:
                url = urljoin(f"{settings.GLPI_BASE_URL}/", path)
                parsed = urlparse(url)
                if parsed.netloc != base.netloc or parsed.scheme != base.scheme:
                    attempts.append({"path": path, "error": "external_document_url_skipped"})
                    continue
                response = self.session.get(
                    url,
                    headers={"Accept": "application/json, text/html;q=0.9"},
                    timeout=settings.GLPI_TIMEOUT_SECONDS,
                    verify=self.verify,
                )
                try:
                    payload = response.json()
                except (TypeError, ValueError):
                    payload = None
                is_schema = isinstance(payload, dict) and "paths" in payload
                attempts.append({"path": path, "http_status": response.status_code, "openapi_document": is_schema})
                if response.status_code < 400 and is_schema:
                    return payload, attempts, documents
                content_type = response.headers.get("Content-Type", "").lower()
                is_html = "html" in content_type
                is_text_document = is_html or "javascript" in content_type or "ecmascript" in content_type or "text/plain" in content_type
                if response.status_code < 400 and is_text_document:
                    document = response.text
                    documents[path.strip("/").replace("/", "-") or "doc"] = document
                    candidates = re.findall(r"(?:url|spec(?:ification)?)[\s:=]+[\"']([^\"']+)", document, flags=re.IGNORECASE)
                    if is_html:
                        candidates += re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", document, flags=re.IGNORECASE)
                    for candidate in candidates:
                        resolved = urljoin(getattr(response, "url", url), candidate)
                        candidate_parsed = urlparse(resolved)
                        candidate_path = candidate_parsed.path + (f"?{candidate_parsed.query}" if candidate_parsed.query else "")
                        if candidate_path and candidate_path not in visited and candidate_path not in queued:
                            queued.append(candidate_path)
            except requests.RequestException as exc:
                attempts.append({"path": path, "error": type(exc).__name__})
        return None, attempts, documents


_client: GlpiClient | None = None


def get_glpi_client() -> GlpiClient:
    global _client
    if _client is None:
        _client = GlpiClient()
    return _client
