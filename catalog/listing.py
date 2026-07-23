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
)

INSTANCE_COLUMNS = (
    ListColumn("name", "Наименование", required=True, default=True),
    ListColumn("instance_type", "Тип", default=True),
    ListColumn("status", "Состояние", default=True),
    ListColumn("catalog_code", "Код"),
    ListColumn("source", "Источник"),
    ListColumn("services", "Услуги"),
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
