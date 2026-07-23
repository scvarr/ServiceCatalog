"""Read-only diagnostic export for the connected GLPI API."""

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from django.conf import settings

from .glpi import GlpiError, get_glpi_client


REDACTED_KEYS = {
    "name", "serial", "otherserial", "uuid", "comment", "description",
    "address", "email", "phone", "contact", "contact_num",
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in REDACTED_KEYS and value not in (None, ""):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(item_key): _redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _endpoint_list(schema: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not schema:
        return []
    result = []
    for path, definition in sorted(schema.get("paths", {}).items()):
        if isinstance(definition, dict):
            methods = sorted(key.upper() for key in definition if key.lower() in HTTP_METHODS)
            result.append({"path": path, "methods": methods})
    return result


def build_glpi_diagnostic_archive(reference) -> bytes:
    """Create a ZIP without mutating GLPI or enumerating endpoint data.

    The OpenAPI document describes all exposed endpoints. Calling every route is
    intentionally avoided: routes can require parameters, permissions, or
    modify data even when their names appear harmless.
    """
    client = get_glpi_client()
    payload: dict[str, Any] | None = None
    computer_error = ""
    try:
        payload = client.get_computer_payload(reference.external_id)
    except GlpiError as exc:
        computer_error = str(exc)
    try:
        schema, schema_probes = client.get_api_schema()
    except GlpiError as exc:
        schema, schema_probes = None, [{"error": str(exc)}]

    endpoints = _endpoint_list(schema)
    manifest = {
        "format": "service-catalog-glpi-diagnostics-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_version": settings.GLPI_API_VERSION,
        "computer_payload_captured": payload is not None,
        "computer_error": computer_error,
        "openapi_captured": schema is not None,
        "endpoint_count": len(endpoints),
        "redaction": "Sample values for identifying and contact fields are replaced with <redacted>.",
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("README.txt", "Read-only GLPI diagnostic package. No endpoint data was enumerated; endpoint definitions come from OpenAPI.\n")
        package.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        package.writestr("schema-probes.json", json.dumps(schema_probes, ensure_ascii=False, indent=2))
        package.writestr("endpoints.json", json.dumps(endpoints, ensure_ascii=False, indent=2))
        if payload is not None:
            package.writestr("computer.sample.json", json.dumps(_redact(payload), ensure_ascii=False, indent=2, default=str))
        if schema is not None:
            package.writestr("openapi.json", json.dumps(schema, ensure_ascii=False, indent=2))
    return archive.getvalue()
