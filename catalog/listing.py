from dataclasses import dataclass
from urllib.parse import urlencode

from django.core.paginator import Paginator


DEFAULT_PAGE_SIZE = 25
PAGE_SIZES = (25, 50, 100)


@dataclass(frozen=True)
class ListColumn:
    key: str
    label: str
    required: bool = False
    default: bool = False


SERVICE_COLUMNS = (
    ListColumn("name", "Наименование", required=True, default=True),
    ListColumn("instance_count", "Экземпляров", default=True),
    ListColumn("accounting_mode", "Учёт", default=True),
    ListColumn("code", "Код"),
    ListColumn("description", "Описание"),
    ListColumn("is_active", "Активна"),
    ListColumn("contract_quantity", "По договору"),
    ListColumn("actual_quantity", "Актуально"),
    ListColumn("contract_delta", "Расхождение"),
    ListColumn("contract_status", "Статус по договору", default=True),
    ListColumn("composition_delta", "Изменения состава"),
)

INSTANCE_COLUMNS = (
    ListColumn("name", "Наименование", required=True, default=True),
    ListColumn("instance_type", "Тип", default=True),
    ListColumn("status", "Состояние", default=True),
    ListColumn("catalog_code", "Код"),
    ListColumn("source", "Источник"),
    ListColumn("services", "Услуги"),
    ListColumn("profile_model", "Модель"),
    ListColumn("cpu_summary", "Процессор"),
    ListColumn("memory_total", "Память, ГБ"),
    ListColumn("raid_controller", "RAID"),
    ListColumn("hypervisor", "Гипервизор"),
    ListColumn("commissioned", "Ввод в эксплуатацию"),
    ListColumn("risk_level", "Риск"),
    ListColumn("replacement_year", "План замены"),
)

SERVICE_MEMBERSHIP_COLUMNS = (
    ListColumn("name", "Экземпляр", required=True, default=True),
    ListColumn("instance_type", "Тип", default=True),
    ListColumn("included_at", "Включен", default=True),
    ListColumn("catalog_code", "Код"),
    ListColumn("source", "Источник"),
    ListColumn("profile_model", "Модель"),
    ListColumn("cpu_summary", "Процессор"),
    ListColumn("memory_total", "Память, ГБ"),
    ListColumn("raid_controller", "RAID"),
    ListColumn("risk_level", "Риск"),
)

GLPI_COMPUTER_COLUMNS = (
    ListColumn("external_name", "Имя в GLPI", default=True),
    ListColumn("inventory_number", "Инвентарный номер", default=True),
    ListColumn("manufacturer_model", "Производитель / модель", default=True),
    ListColumn("external_status", "Статус GLPI", default=True),
    ListColumn("location", "Местоположение", default=True),
    ListColumn("last_synced_at", "Последняя синхронизация", default=True),
    ListColumn("serial_number", "Серийный номер"),
    ListColumn("external_uuid", "UUID"),
    ListColumn("external_type", "Тип GLPI"),
    ListColumn("entity_name", "Сущность"),
    ListColumn("comment", "Комментарий"),
    ListColumn("inventory_source", "Источник инвентаризации"),
    ListColumn("external_created_at", "Создан в GLPI"),
    ListColumn("external_updated_at", "Изменён в GLPI"),
    ListColumn("last_inventory_update", "Последняя инвентаризация"),
    ListColumn("last_boot", "Последняя загрузка"),
    ListColumn("sync_status", "Статус синхронизации"),
    ListColumn("external_url", "Ссылка"),
)


def normalize_page_size(value, fallback=DEFAULT_PAGE_SIZE):
    try:
        page_size = int(value)
    except (TypeError, ValueError):
        return fallback
    return page_size if page_size in PAGE_SIZES else fallback


def normalize_columns(values, columns):
    requested = set(values or ())
    return [column.key for column in columns if column.required or column.key in requested]


def default_columns(columns):
    return [column.key for column in columns if column.default]


def visible_columns(values, columns):
    if values is None:
        return default_columns(columns)
    normalized = normalize_columns(values, columns)
    return normalized


def column_specs(keys, columns):
    allowed = {column.key: column for column in columns}
    return [allowed[key] for key in keys if key in allowed]


def paginate(queryset, page_number, page_size):
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page_number)
    return page_obj, paginator.get_elided_page_range(page_obj.number)


def query_string(data, allowed_params, *, exclude=()):
    excluded = set(exclude)
    pairs = []
    for key in allowed_params:
        if key in excluded:
            continue
        value = data.get(key, "")
        if value not in (None, ""):
            pairs.append((key, value))
    return urlencode(pairs)
