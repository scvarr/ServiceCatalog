"""Read-only access to component data stored in a GLPI MySQL database.

The GLPI High-Level API is preferred.  Some installations, however, return an
empty processor collection although the regular GLPI interface shows the
components.  This module supplies a deliberately narrow fallback for that
case.  It never writes to GLPI and does not use Django's database connection.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings


class GlpiDatabaseError(Exception):
    """Safe error suitable for the import journal and user-facing status."""


class GlpiDatabaseDisabled(GlpiDatabaseError):
    pass


class GlpiDatabaseClient:
    def _require_config(self) -> None:
        if not settings.GLPI_DB_ENABLED:
            raise GlpiDatabaseDisabled("Прямое чтение базы GLPI отключено.")
        if not all((settings.GLPI_DB_HOST, settings.GLPI_DB_NAME, settings.GLPI_DB_USER, settings.GLPI_DB_PASSWORD)):
            raise GlpiDatabaseError("Конфигурация прямого чтения базы GLPI неполная.")

    def get_computer_processors(self, computer_id: int | str) -> list[dict[str, Any]]:
        """Return active processor component rows for one GLPI Computer.

        The query is intentionally fixed and parameterized: the external ID
        never becomes SQL text.  It is based on GLPI tables verified against
        the deployed schema (items_deviceprocessors/deviceprocessors).
        """
        self._require_config()
        try:
            import pymysql
        except ImportError as exc:  # pragma: no cover - image dependency guard
            raise GlpiDatabaseError("В образе приложения отсутствует клиент MySQL.") from exc

        query = """
            SELECT
                link.id AS component_link_id,
                link.items_id AS computer_id,
                processor.id AS processor_id,
                processor.designation,
                COALESCE(NULLIF(link.frequency, 0), processor.frequence) AS frequency_mhz,
                COALESCE(link.nbcores, processor.nbcores_default, 0) AS nbcores,
                COALESCE(link.nbthreads, processor.nbthreads_default, 0) AS nbthreads
            FROM glpi_items_deviceprocessors AS link
            JOIN glpi_deviceprocessors AS processor
              ON processor.id = link.deviceprocessors_id
            WHERE link.itemtype = 'Computer'
              AND link.items_id = %s
              AND link.is_deleted = 0
            ORDER BY link.id
        """
        try:
            connection = pymysql.connect(
                host=settings.GLPI_DB_HOST,
                port=settings.GLPI_DB_PORT,
                user=settings.GLPI_DB_USER,
                password=settings.GLPI_DB_PASSWORD,
                database=settings.GLPI_DB_NAME,
                connect_timeout=settings.GLPI_DB_TIMEOUT_SECONDS,
                read_timeout=settings.GLPI_DB_TIMEOUT_SECONDS,
                write_timeout=settings.GLPI_DB_TIMEOUT_SECONDS,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )
            try:
                with connection.cursor() as cursor:
                    cursor.execute(query, (computer_id,))
                    return list(cursor.fetchall())
            finally:
                connection.close()
        except pymysql.MySQLError as exc:
            raise GlpiDatabaseError(f"Не удалось прочитать компоненты из базы GLPI: {type(exc).__name__}.") from exc


_client: GlpiDatabaseClient | None = None


def get_glpi_database_client() -> GlpiDatabaseClient:
    global _client
    if _client is None:
        _client = GlpiDatabaseClient()
    return _client
