from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

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
        token = self._token()
        try:
            response = self.session.get(
                f"{settings.GLPI_BASE_URL}/api.php/{settings.GLPI_API_VERSION}/Assets/Computer/{computer_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=settings.GLPI_TIMEOUT_SECONDS, verify=self.verify,
            )
            response.raise_for_status()
            return normalize_computer(response.json())
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise GlpiError(f"GLPI вернул HTTP {status} при получении компьютера.") from exc
        except requests.RequestException as exc:
            raise GlpiError(f"Не удалось получить компьютер из GLPI: {type(exc).__name__}.") from exc
        except (TypeError, ValueError, KeyError) as exc:
            raise GlpiError("GLPI вернул некорректные данные компьютера.") from exc


_client: GlpiClient | None = None


def get_glpi_client() -> GlpiClient:
    global _client
    if _client is None:
        _client = GlpiClient()
    return _client
